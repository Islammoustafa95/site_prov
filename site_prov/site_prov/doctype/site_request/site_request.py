from frappe.model.document import Document
import frappe
from frappe.utils import now
import json

class SiteRequest(Document):
    def validate(self):
        if not self.creation_date:
            self.creation_date = now()
        if not self.owner_email:
            self.owner_email = frappe.session.user

    def on_update(self):
        # Update installed apps list whenever status changes to Active
        if self.status == "Active" and not self.installed_apps:
            try:
                # Run bench command to list apps
                apps = frappe.utils.execute_in_shell(f"bench --site {self.subdomain}.ventotech.co list-apps")[1]
                self.installed_apps = json.dumps(apps.strip().split("\n"))
                self.db_update()
            except:
                pass