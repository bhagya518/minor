import os
import shutil

source_dir = r"c:\Users\bhagy\Downloads\minor-project-main"
target_dir = r"c:\Users\bhagy\Downloads\minor-project-main\clean_project"

# Ensure target directory exists
os.makedirs(target_dir, exist_ok=True)

folders_to_copy = ["blockchain", "node_service", "models", "dashboard"]
files_to_copy = [
    "setup_network.py",
    "start_8_nodes.bat",
    "start_nodes.bat",
    "requirements.txt",
    ".env.example",
    "README.md",
    "RUN_SYSTEM.md"
]

def ignore_files(dir_path, contents):
    # Ignore node_modules to avoid copying huge amounts of data
    if "node_modules" in contents:
        return ["node_modules"]
    # Also ignore python cache
    ignored = []
    for c in contents:
        if c == "__pycache__" or c == ".pytest_cache" or c.endswith(".pyc"):
            ignored.append(c)
    return ignored

print(f"Creating clean project in {target_dir}...")

for folder in folders_to_copy:
    src_folder = os.path.join(source_dir, folder)
    dst_folder = os.path.join(target_dir, folder)
    if os.path.exists(src_folder):
        print(f"Copying folder: {folder}")
        if os.path.exists(dst_folder):
            shutil.rmtree(dst_folder)
        shutil.copytree(src_folder, dst_folder, ignore=ignore_files)
    else:
        print(f"Warning: Folder {folder} not found.")

for file in files_to_copy:
    src_file = os.path.join(source_dir, file)
    dst_file = os.path.join(target_dir, file)
    if os.path.exists(src_file):
        print(f"Copying file: {file}")
        shutil.copy2(src_file, dst_file)
    else:
        print(f"Warning: File {file} not found.")

print("Done creating clean project.")
