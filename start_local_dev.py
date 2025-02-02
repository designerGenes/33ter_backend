import iterm2
import asyncio
import os

async def activate_venv(session):
    """Deactivate conda and activate the project's venv."""
    app_dir = "/Users/jadennation/DEV/chatterbox/app"
    venv_path = os.path.join(app_dir, "venv")
    
    if not os.path.exists(venv_path):
        print(f"Error: Virtual environment not found at {venv_path}")
        raise RuntimeError("Virtual environment not found")
    
    await session.async_send_text("cd /Users/jadennation/DEV/chatterbox/app\n")
    await session.async_send_text("conda deactivate 2>/dev/null || true\n")  # Suppress potential errors
    await session.async_send_text("source venv/bin/activate\n")
    await session.async_send_text("echo $VIRTUAL_ENV | grep -q 'venv' && echo 'Virtual environment successfully activated!' || echo 'Failed to activate virtual environment'\n")

async def main(connection):
    try:
        app = await iterm2.async_get_app(connection)
        window = await iterm2.Window.async_create(connection)
        initial_session = window.current_tab.current_session

        # Configure Screenshot Taker pane
        await initial_session.async_set_name("screenshot taker")
        await activate_venv(initial_session)
        await initial_session.async_send_text("export RUN_MODE=local\n")
        await initial_session.async_send_text("python3 beginRecording.py\n")

        # Split and configure Screenshot Processor pane
        processor_session = await initial_session.async_split_pane(vertical=False)
        await processor_session.async_set_name("Process Screenshots server")
        await activate_venv(processor_session)
        await processor_session.async_send_text("export RUN_MODE=local\n")
        await processor_session.async_send_text("cd scripts/processStream\n")
        await processor_session.async_send_text("python3 server_process_stream.py\n")

        # Split and configure SocketIO Server pane
        socket_session = await processor_session.async_split_pane(vertical=False)
        await socket_session.async_set_name("SocketIO server")
        await activate_venv(socket_session)
        await socket_session.async_send_text("export RUN_MODE=local\n")
        await socket_session.async_send_text("cd scripts/publishMessage\n")
        await socket_session.async_send_text("python3 server_socketio.py\n")
    
        # Split and configure utility pane
        utility_session = await socket_session.async_split_pane(vertical=False)
        await utility_session.async_set_name("utility")
        await activate_venv(utility_session)

    except RuntimeError as e:
        print(f"Setup failed: {e}")
        sys.exit(1)

# Install iterm2 module if not present
if __name__ == "__main__":
    try:
        import iterm2
    except ImportError:
        print("Installing iterm2 module...")
        os.system("pip3 install iterm2")
        import iterm2
    
    iterm2.run_until_complete(main)
