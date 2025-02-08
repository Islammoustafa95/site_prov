import frappe

def get_context(context):
    if not frappe.session.user or frappe.session.user == 'Guest':
        frappe.throw("Please login to create a site", frappe.PermissionError)
    
    # Get all plans with their apps
    plans = frappe.get_all(
        "Site Plan",
        fields=["name", "plan_name", "monthly_price", "description"],
        order_by="monthly_price asc"
    )
    
    for plan in plans:
        plan.apps = frappe.get_all(
            "Site Plan App",
            filters={"parent": plan.name},
            fields=["app_name"],
            order_by="idx asc"
        )
    
    context.plans = plans