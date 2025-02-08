# site_prov/site_prov/hooks.py
app_name = "site_prov"
app_title = "Site Provisioning"
app_publisher = "your_name"
app_description = "Multi-site provisioning system for ERPNext"
app_email = "your_email"
app_license = "MIT"

# Website
website_route_rules = [
    {"from_route": "/create-site", "to_route": "create-site"},
    {"from_route": "/my-sites", "to_route": "my-sites"}
]

# DocType JS
doctype_js = {
    "Site Request": "public/js/site_request.js"
}

# Include JS/CSS in web pages
web_include_js = [
    "/assets/site_prov/js/site_request.js"
]

# Permission Settings
has_permission = {
    "Site Request": "site_prov.api.has_site_permission"
}

# DocTypes to expose via API
allowed_to_export = [
    "Site Request",
    "Site Plan"
]