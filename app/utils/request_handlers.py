import os

from flask import g


def cleanup_tts_files(response):
    try:
        if hasattr(g, 'tts_filename') and os.path.exists(g.tts_filename):
            try:
                os.remove(g.tts_filename)
                print(f"Deleted file: {g.tts_filename}")
            except Exception as e:
                print(f"Failed to delete file: {str(e)}")
        return response
    except Exception as e:
        print(f"Error in cleanup_tts_files: {str(e)}")
        return response
