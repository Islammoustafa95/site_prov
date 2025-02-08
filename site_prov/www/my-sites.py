# site_prov/site_prov/www/my-sites.py
import frappe

def get_context(context):
    if not frappe.session.user or frappe.session.user == 'Guest':
        frappe.throw("Please login to view your sites", frappe.PermissionError)
    
    # Get all sites for current user
    sites = frappe.get_all(
        "Site Request",
        filters={
            "owner": frappe.session.user,
            "status": ["!=", "Failed"]
        },
        fields=["name", "subdomain", "plan", "status", "creation_date", "installed_apps"],
        order_by="creation_date desc"
    )
    
    # Get all plans for upgrade/downgrade options
    plans = frappe.get_all(
        "Site Plan",
        fields=["name", "plan_name", "monthly_price"],
        order_by="monthly_price asc"
    )
    
    context.sites = sites
    context.plans = plans