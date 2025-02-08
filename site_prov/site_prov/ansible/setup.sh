# site_prov/site_prov/ansible/setup.sh
#!/bin/bash

# Install Ansible if not present
if ! command -v ansible &> /dev/null; then
    sudo apt update
    sudo apt install -y ansible
fi

# Install required collections
ansible-galaxy collection install -r requirements.yml

# Ensure correct permissions
chmod +x site_setup.yml