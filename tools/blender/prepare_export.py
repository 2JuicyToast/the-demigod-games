"""Starter Blender automation script for The Demigod Games.

Run this inside Blender's scripting workspace after adapting the TODO sections.
"""

import bpy


PROJECT_NAME = "The Demigod Games"


def prepare_scene() -> None:
    """Prepare the current Blender scene for a Roblox export."""
    # TODO: Add project-specific transforms, naming, and cleanup rules.
    print(f"Preparing scene for {PROJECT_NAME}")


def export_selected_objects(output_path: str) -> None:
    """Export selected objects as FBX after configuring project settings."""
    # TODO: Confirm export settings with the art team before enabling this.
    bpy.ops.export_scene.fbx(filepath=output_path, use_selection=True)


if __name__ == "__main__":
    prepare_scene()
    # TODO: Set an output path and call export_selected_objects(...).
