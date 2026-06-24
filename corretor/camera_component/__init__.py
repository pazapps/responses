import os
import streamlit.components.v1 as components

_dir = os.path.join(os.path.dirname(__file__), "frontend")
_camera_component = components.declare_component("camera_component", path=_dir)

def camera_component(key=None, height=700):
    """Render the camera component. Returns a data URL (string) when an image is confirmed, otherwise None."""
    return _camera_component(key=key, default=None, height=height)
