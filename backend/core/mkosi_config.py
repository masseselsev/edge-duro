import os
from models import Recipe


def generate_mkosi_conf(recipe: Recipe, workspace_path: str) -> str:
    """
    Generates mkosi.conf configuration for systemd image builder.
    """
    pkgs = list(recipe.packages) if recipe.packages else ["systemd", "systemd-sysv", "dbus", "iproute2"]
    if "systemd-boot" not in pkgs:
        pkgs.append("systemd-boot")
    packages_formatted = "\n    ".join(pkgs)

    arch_map = {
        "amd64": "x86-64",
        "x86_64": "x86-64",
        "x86-64": "x86-64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    mkosi_arch = arch_map.get((recipe.architecture or "amd64").lower(), "x86-64")

    if (recipe.distribution or "").lower() == "debian":
        components = "main contrib non-free non-free-firmware"
    elif (recipe.distribution or "").lower() == "ubuntu":
        components = "main restricted universe multiverse"
    else:
        components = "main"

    config_lines = [
        "[Distribution]",
        f"Distribution={recipe.distribution}",
        f"Release={recipe.release}",
        f"Architecture={mkosi_arch}",
        f"Repositories={components}",
        "",
        "[Build]",
        "CacheDirectory=/opt/data/duro_workspace/cache",
        "",
        "[Output]",
        f"ImageId={recipe.name.lower().replace(' ', '_')}",
        "Format=disk",
        "OutputDirectory=output",
        "",
        "[Content]",
        f"Packages=\n    {packages_formatted}",
        "Autologin=yes",
    ]

    if recipe.kernel_params and recipe.kernel_params.strip():
        config_lines.append(f"KernelCommandLine={recipe.kernel_params.strip()}")

    if recipe.raw_mkosi_conf and recipe.raw_mkosi_conf.strip():
        config_lines.append("\n# Custom Raw Override")
        config_lines.append(recipe.raw_mkosi_conf.strip())

    content = "\n".join(config_lines) + "\n"

    conf_path = os.path.join(workspace_path, "mkosi.conf")
    with open(conf_path, "w") as f:
        f.write(content)

    return content
