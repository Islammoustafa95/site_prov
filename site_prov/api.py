# site_prov/site_prov/api.py
import frappe
import os
import json
import requests
from frappe.utils import now
import subprocess
from frappe.utils.password import get_random_password

def create_cloudflare_record(subdomain):
    try:
        api_token = frappe.conf.get("cloudflare_api_token")
        zone_id = frappe.conf.get("cloudflare_zone_id")
        server_ip = frappe.conf.get("server_ip")

        if not all([api_token, zone_id, server_ip]):
            raise Exception("Cloudflare configuration missing in common_site_config.json")

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        data = {
            "type": "A",
            "name": subdomain,
            "content": server_ip,
            "proxied": True
        }

        response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            headers=headers,
            json=data
        )

        if not response.ok:
            raise Exception(f"Cloudflare API error: {response.text}")

        return True

    except Exception as e:
        raise Exception(f"Failed to create Cloudflare DNS record: {str(e)}")

def delete_cloudflare_record(subdomain):
    try:
        api_token = frappe.conf.get("cloudflare_api_token")
        zone_id = frappe.conf.get("cloudflare_zone_id")

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        # First get the record ID
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            headers=headers,
            params={"name": f"{subdomain}.ventotech.co"}
        )

        if not response.ok:
            raise Exception(f"Cloudflare API error: {response.text}")

        records = response.json().get('result', [])
        if not records:
            return True  # Record doesn't exist, nothing to delete

        record_id = records[0]['id']

        # Delete the record
        response = requests.delete(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
            headers=headers
        )

        if not response.ok:
            raise Exception(f"Cloudflare API error: {response.text}")

        return True

    except Exception as e:
        raise Exception(f"Failed to delete Cloudflare DNS record: {str(e)}")

def send_success_email(email, site_name, admin_password):
    try:
        frappe.sendmail(
            recipients=[email],
            subject=f"Your site {site_name} is ready!",
            message=f"""
            Hello,

            Your new site has been created successfully!

            Site URL: https://{site_name}
            Username: administrator
            Password: {admin_password}

            Please change your password after first login.

            Best regards,
            Your Site Creation Team
            """
        )
    except Exception as e:
        frappe.log_error(f"Email sending error: {str(e)}", "Site Creation Email Error")

def send_failure_email(email, site_name):
    try:
        frappe.sendmail(
            recipients=[email],
            subject=f"Site creation failed for {site_name}",
            message=f"""
            Hello,

            Unfortunately, we encountered an error while creating your site {site_name}.
            Our team has been notified and will investigate the issue.

            We will contact you once we have more information.

            Best regards,
            Your Site Creation Team
            """
        )
    except Exception as e:
        frappe.log_error(f"Email sending error: {str(e)}", "Site Creation Email Error")

@frappe.whitelist()
def create_site(subdomain, plan):
    try:
        # Validate permissions
        if not frappe.has_permission("Site Request", "create"):
            frappe.throw("Not permitted", frappe.PermissionError)

        site_name = f"{subdomain}.ventotech.co"

        # Check if site exists
        if frappe.db.exists("Site Request", {"subdomain": subdomain}):
            frappe.throw("Subdomain already exists")

        # Create DNS record
        create_cloudflare_record(subdomain)

        # Create site request
        site_request = frappe.get_doc({
            "doctype": "Site Request",
            "subdomain": subdomain,
            "plan": plan,
            "owner_email": frappe.session.user,
            "status": "Processing",
            "creation_date": now(),
            "creation_log": "DNS Record created. Starting site creation..."
        })
        site_request.insert(ignore_permissions=True)

        # Get MySQL root password
        mysql_password = frappe.conf.get('mysql_root_password')
        if not mysql_password:
            raise Exception("MySQL root password not configured")

        # Generate admin password
        admin_password = get_random_password()

        # Run ansible playbook
        ansible_cmd = [
            "ansible-playbook",
            f"{frappe.get_app_path('site_prov', 'ansible', 'site_setup.yml')}",
            "-e", f"site_name={site_name}",
            "-e", f"admin_password={admin_password}",
            "-e", f"mysql_password={mysql_password}",
            "-e", f"plan={plan}",
            "-e", f"subdomain={subdomain}"
        ]

        process = subprocess.Popen(
            ansible_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        def update_log():
            try:
                output, error = process.communicate()
                log = output.decode() if output else ""
                if error:
                    log += f"\nErrors:\n{error.decode()}"

                site_request.creation_log += f"\n{log}"
                
                if process.returncode == 0:
                    site_request.status = "Active"
                    # Send success email
                    send_success_email(site_request.owner_email, site_name, admin_password)
                else:
                    site_request.status = "Failed"
                    # Send failure email
                    send_failure_email(site_request.owner_email, site_name)
                
                site_request.save()
            except Exception as e:
                frappe.log_error(f"Log update error: {str(e)}", "Site Creation Log Update Error")

        # Schedule log update
        frappe.enqueue(
            update_log,
            queue='long',
            timeout=3600
        )

        return {
            "status": "success",
            "message": "Site creation initiated"
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Site Creation Error")
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def change_plan(site_request, new_plan, action):
    try:
        site = frappe.get_doc("Site Request", site_request)
        
        if not site.has_permission("write"):
            frappe.throw("Not permitted", frappe.PermissionError)

        if site.status != "Active":
            frappe.throw("Site must be active to change plans")

        site_name = f"{site.subdomain}.ventotech.co"
        
        # Get current and new plan details
        current_plan = frappe.get_doc("Site Plan", site.plan)
        new_plan_doc = frappe.get_doc("Site Plan", new_plan)
        
        # Get app differences
        current_apps = [app.app_name for app in current_plan.included_apps]
        new_apps = [app.app_name for app in new_plan_doc.included_apps]
        
        if action == "upgrade":
            apps_to_install = list(set(new_apps) - set(current_apps))
            ansible_tags = "install_apps"
        else:  # downgrade
            apps_to_remove = list(set(current_apps) - set(new_apps))
            ansible_tags = "remove_apps"

        # Run ansible playbook for plan change
        ansible_cmd = [
            "ansible-playbook",
            f"{frappe.get_app_path('site_prov', 'ansible', 'site_setup.yml')}",
            "-e", f"site_name={site_name}",
            "-e", f"apps_to_install={','.join(apps_to_install) if action == 'upgrade' else ''}",
            "-e", f"apps_to_remove={','.join(apps_to_remove) if action == 'downgrade' else ''}",
            "--tags", ansible_tags
        ]

        process = subprocess.Popen(
            ansible_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        output, error = process.communicate()

        if process.returncode == 0:
            # Update site record
            site.plan = new_plan
            site.creation_log += f"\nPlan changed from {current_plan.plan_name} to {new_plan_doc.plan_name}"
            site.save()

            return {
                "status": "success",
                "message": "Plan changed successfully"
            }
        else:
            raise Exception(f"Plan change failed: {error.decode()}")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Plan Change Error")
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def delete_site(site_request):
    try:
        site = frappe.get_doc("Site Request", site_request)
        
        if not site.has_permission("delete"):
            frappe.throw("Not permitted", frappe.PermissionError)

        site_name = f"{site.subdomain}.ventotech.co"

        # Run ansible playbook for site deletion
        ansible_cmd = [
            "ansible-playbook",
            f"{frappe.get_app_path('site_prov', 'ansible', 'site_setup.yml')}",
            "-e", f"site_name={site_name}",
            "--tags", "delete_site"
        ]

        process = subprocess.Popen(
            ansible_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        output, error = process.communicate()

        if process.returncode == 0:
            # Delete Cloudflare record
            delete_cloudflare_record(site.subdomain)
            
            # Delete site record
            site.delete()

            return {
                "status": "success",
                "message": "Site deleted successfully"
            }
        else:
            raise Exception(f"Site deletion failed: {error.decode()}")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Site Deletion Error")
        return {
            "status": "error",
            "message": str(e)
        }