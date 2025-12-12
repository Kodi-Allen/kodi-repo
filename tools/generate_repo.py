#!/usr/bin/env python3
import os
import hashlib
import xml.etree.ElementTree as ET
from xml.dom import minidom
import zipfile

def get_addon_dirs():
    addons = []
    for item in os.listdir('.'):
        if os.path.isdir(item) and not item.startswith('.') and not item == 'tools':
            addon_xml = os.path.join(item, 'addon.xml')
            if os.path.exists(addon_xml):
                addons.append(item)
    return addons

def create_addon_zip(addon_dir):
    tree = ET.parse(os.path.join(addon_dir, 'addon.xml'))
    root = tree.getroot()
    addon_id = root.get('id')
    version = root.get('version')
    
    zip_filename = f"{addon_id}-{version}.zip"
    zip_path = os.path.join(addon_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root_dir, dirs, files in os.walk(addon_dir):
            if root_dir == addon_dir:
                files = [f for f in files if not f.endswith('.zip')]
            
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.join(addon_id, os.path.relpath(file_path, addon_dir))
                zipf.write(file_path, arcname)
    
    print(f"✓ Created: {zip_filename}")
    return zip_filename

def generate_addons_xml():
    addons = get_addon_dirs()
    
    if not addons:
        print("No addons found!")
        return
    
    print(f"\nFound addons: {len(addons)}")
    print("=" * 50)
    
    root = ET.Element('addons')
    
    for addon_dir in sorted(addons):
        print(f"\nProcessing: {addon_dir}")
        create_addon_zip(addon_dir)
        
        addon_xml_path = os.path.join(addon_dir, 'addon.xml')
        tree = ET.parse(addon_xml_path)
        addon_element = tree.getroot()
        root.append(addon_element)
        
        addon_id = addon_element.get('id')
        version = addon_element.get('version')
        print(f"  ID: {addon_id}")
        print(f"  Version: {version}")
    
    xml_string = ET.tostring(root, encoding='unicode')
    dom = minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent='  ')
    pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])
    
    with open('addons.xml', 'w', encoding='utf-8') as f:
        f.write(pretty_xml)
    
    print("\n" + "=" * 50)
    print("✓ addons.xml created")
    generate_md5()

def generate_md5():
    with open('addons.xml', 'rb') as f:
        md5_hash = hashlib.md5(f.read()).hexdigest()
    
    with open('addons.xml.md5', 'w') as f:
        f.write(md5_hash)
    
    print(f"✓ addons.xml.md5 created: {md5_hash}")

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("Kodi Repository Generator")
    print("=" * 50)
    generate_addons_xml()
    print("\n" + "=" * 50)
    print("Done!")
    print("=" * 50)
