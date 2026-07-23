import os
from models import Recipe


def generate_mkosi_conf(recipe: Recipe, workspace_path: str) -> str:
    """
    Generates mkosi.conf configuration for systemd image builder.
    """
    packages_str = " ".join(recipe.packages) if recipe.packages else "systemd systemd-sysv dbus iproute2"

    config_lines = [
        "[Distribution]",
        f"Distribution={recipe.distribution}",
        f"Release={recipe.release}",
        f"Architecture={recipe.architecture}",
        "",
        "[Output]",
        f"ImageId={recipe.name.lower().replace(' ', '_')}",
        "Format=disk",
        "OutputDirectory=output",
        "",
        "[Content]",
        f"Packages={packages_str}",
        f"HostName={recipe.hostname}",
        "Autologin=yes",
        "",
        "[Validation]",
        "BTRFS=no",
    ]

    # If raw mkosi.conf override provided by user in Advanced Editor
    if recipe.raw_mkosi_conf and recipe.raw_mkosi_conf.strip():
        config_lines.append("\n# Custom Raw Override")
        config_lines.append(recipe.raw_mkosi_conf.strip())

    content = "\n".join(config_lines) + "\n"

    conf_path = os.path.join(workspace_path, "mkosi.conf")
    with open(conf_path, "w") as f:
        f.write(content)

    return content
