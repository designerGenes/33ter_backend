#!/usr/bin/env python3
"""Threethreeter Process Manager Entry Point

This script serves as the main entry point for the Threethreeter application. It initializes and
manages all core services including screenshot capture, OCR processing, and Socket.IO
communication. It provides a terminal-based UI for monitoring and controlling these services.

Key Features:
- Service initialization and management
- Configuration loading and validation
- Logging setup and management
- Terminal UI initialization
- System requirement validation
- Graceful shutdown handling

#TODO:
- Add proper signal handling for graceful shutdown
- Implement service recovery mechanisms
- Add proper resource cleanup on exit
- Consider adding daemon mode support
- Add proper process isolation
- Implement proper error reporting
"""

import curses
import sys
import argparse
import logging
import traceback
from typing import Optional
import os
import tempfile
import signal
import subprocess
import errno
import time
import json
import socket

try:
    # Use explicit relative imports since this script is inside the Threethreeter package
    from .system_check import print_system_status
    from .config_loader import config
    from .process_manager import ProcessManager
    from .terminal_ui import TerminalUI
except ImportError as e:
    print(f"Error importing required modules: {e}", file=sys.stderr)
    print("Please ensure you're running from the correct directory and all dependencies are installed.", file=sys.stderr)
    sys.exit(1)

# Get a logger instance for this module specifically
module_logger = logging.getLogger(__name__)

def setup_logging():
    logging.root.handlers = []
    logging.basicConfig(level=logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    
    # Create a file handler for the root logger
    root_file_handler = logging.FileHandler("root.log")
    root_file_handler.setLevel(logging.INFO)
    root_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    root_file_handler.setFormatter(root_formatter)
    
    # Remove all handlers and add only the file handler
    root_logger.handlers = []
    root_logger.addHandler(root_file_handler)
    
    # Set level for other modules
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("engineio").setLevel(logging.ERROR)
    logging.getLogger(" ").setLevel(logging.ERROR)

def setup_environment() -> Optional[ProcessManager]:
    """Initialize application environment and process manager."""
    try:
        # Tesseract installation is assumed to be handled by Homebrew and available in PATH.
        # TESSDATA_PREFIX is also assumed to be configured correctly by the Homebrew installation.

        # Check for critical configuration
        try:
            sc_config = config.get('screenshot', None)
            if sc_config is None:
                module_logger.warning("No screenshot configuration found, using defaults")
                config.set('screenshot', 'frequency', 4.0)
                config.set('screenshot', 'cleanup_age', 180)
        except Exception as config_error:
            module_logger.warning(f"Error checking screenshot configuration: {config_error}")
            config.set('screenshot', 'frequency', 4.0)
            config.set('screenshot', 'cleanup_age', 180)

        # Initialize process manager
        process_manager = ProcessManager()
        return process_manager
    except Exception as e:
        module_logger.error(f"Failed to initialize environment: {e}", exc_info=True)
        return None

def check_silent_process_status(pid_file_path: str) -> dict:
    """Check if silent process is running and get basic status info."""
    status = {
        "silent_process_running": False,
        "pid": None,
        "server_responding": False,
        "server_host": None,
        "server_port": None,
        "error": None
    }
    
    # Check if PID file exists and process is running
    if os.path.exists(pid_file_path):
        try:
            with open(pid_file_path, "r") as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    status["pid"] = pid
                    
                    # Check if process is actually running
                    try:
                        if os.name == 'nt':
                            # Windows: use tasklist
                            result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                                  capture_output=True, text=True, timeout=5)
                            status["silent_process_running"] = str(pid) in result.stdout
                        else:
                            # Unix: send signal 0 to check if process exists
                            os.kill(pid, 0)
                            status["silent_process_running"] = True
                    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                        status["silent_process_running"] = False
                        status["error"] = "Process not found (stale PID file)"
        except (ValueError, IOError) as e:
            status["error"] = f"Error reading PID file: {e}"
    else:
        status["error"] = "No PID file found"
    
    # Check server status
    try:
        from .server_config import get_server_config
        server_config = get_server_config()
        if server_config and 'server' in server_config:
            server_cfg = server_config['server']
            host = server_cfg.get('host', '0.0.0.0')
            port = server_cfg.get('port', 5348)
            
            # Convert 0.0.0.0 to localhost for connection test
            test_host = '127.0.0.1' if host == '0.0.0.0' else host
            status["server_host"] = test_host
            status["server_port"] = port
            
            # Quick socket test
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((test_host, port))
            sock.close()
            
            status["server_responding"] = (result == 0)
        else:
            status["error"] = "Server configuration not available"
    except Exception as e:
        status["error"] = f"Server check failed: {e}"
    
    return status

def print_status_info():
    """Print current application status information."""
    PID_FILE_PATH = os.path.join(tempfile.gettempdir(), "threethreeter_silent.pid")
    
    print("Threethreeter Status Information")
    print("=" * 40)
    
    # Check silent process
    status = check_silent_process_status(PID_FILE_PATH)
    
    if status["silent_process_running"]:
        print(f"✓ Silent process running (PID: {status['pid']})")
    else:
        print("✗ Silent process not running")
        if status["error"]:
            print(f"  └─ {status['error']}")
    
    # Server status
    if status["server_responding"]:
        print(f"✓ Socket.IO server responding ({status['server_host']}:{status['server_port']})")
    else:
        print(f"✗ Socket.IO server not responding ({status['server_host']}:{status['server_port']})")
    
    # Try to get more detailed status if server is responding
    if status["server_responding"]:
        try:
            # Import here to avoid startup dependencies for info command
            import socketio
            
            # Quick client connection to get status
            client = socketio.Client(logger=False, engineio_logger=False)
            client_count = "unknown"
            connection_successful = False
            
            @client.event
            def connect():
                nonlocal connection_successful
                connection_successful = True
            
            @client.on('client_count')
            def on_client_count(data):
                nonlocal client_count
                client_count = data.get('count', 'unknown')
            
            try:
                server_url = f"http://{status['server_host']}:{status['server_port']}"
                client.connect(server_url, wait_timeout=3)
                
                if connection_successful:
                    # Give a moment for any immediate client_count messages
                    time.sleep(0.5)
                    print(f"✓ Socket.IO connection successful")
                    if client_count != "unknown":
                        print(f"  └─ Connected clients: {client_count}")
                    else:
                        print(f"  └─ Client count: not available")
                else:
                    print("✗ Socket.IO connection failed")
                
                client.disconnect()
            except Exception as client_error:
                print(f"✗ Socket.IO detailed check failed: {client_error}")
                
        except ImportError:
            print("  └─ Detailed Socket.IO check unavailable (socketio not imported)")
        except Exception as detailed_error:
            print(f"  └─ Detailed check error: {detailed_error}")
    
    # Configuration info
    print("\nConfiguration:")
    try:
        from .server_config import get_server_config
        server_config = get_server_config()
        if server_config and 'server' in server_config:
            server_cfg = server_config['server']
            print(f"  Server: {server_cfg.get('host', 'N/A')}:{server_cfg.get('port', 'N/A')}")
            print(f"  Room: {server_cfg.get('room', 'N/A')}")
            
            # Try to get screenshot config
            try:
                from .config_loader import config
                screenshot_config = config.get('screenshot', {})
                print(f"  Screenshot frequency: {screenshot_config.get('frequency', 'N/A')}s")
            except Exception:
                print(f"  Screenshot frequency: N/A")
        else:
            print("  Configuration: Not available")
    except Exception as config_error:
        print(f"  Configuration error: {config_error}")
    
    # Summary line
    print("\nSummary:")
    if status["silent_process_running"] and status["server_responding"]:
        print("✓ Threethreeter is running normally")
    elif status["silent_process_running"] and not status["server_responding"]:
        print("⚠ Process running but server not responding")
    elif not status["silent_process_running"] and status["server_responding"]:
        print("⚠ Server responding but no silent process found")
    else:
        print("✗ Threethreeter is not running")

def stop_silent_process(pid_file_path: str) -> int:
    """Stop a running silent mode process using its PID file."""
    if not os.path.exists(pid_file_path):
        print("No silent process PID file found. Process may not be running.")
        return 0
    
    try:
        with open(pid_file_path, "r") as f:
            pid_str = f.read().strip()
            if not pid_str:
                print("PID file is empty. Removing stale file.")
                os.remove(pid_file_path)
                return 0
            
            pid = int(pid_str)
            print(f"Found silent process with PID {pid}. Attempting to stop...")
            
            # Check if process is actually running first
            process_running = False
            try:
                if os.name == 'nt':
                    # Windows: use tasklist
                    result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                          capture_output=True, text=True, timeout=5)
                    process_running = str(pid) in result.stdout
                else:
                    # Unix: send signal 0 to check if process exists
                    os.kill(pid, 0)
                    process_running = True
            except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                process_running = False
            
            if not process_running:
                print(f"Process {pid} is not running. Removing stale PID file.")
                os.remove(pid_file_path)
                return 0
            
            # Attempt to terminate the process
            try:
                if os.name == 'nt':
                    # Windows: use taskkill
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                                 check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"Termination signal sent to process {pid} (Windows).")
                else:
                    # Unix: send SIGTERM
                    os.kill(pid, signal.SIGTERM)
                    print(f"Termination signal sent to process {pid} (Unix).")
                
                # Wait a moment for the process to terminate
                print("Waiting for process to stop...")
                time.sleep(2.0)
                
                # Verify the process has stopped
                process_still_running = False
                try:
                    if os.name == 'nt':
                        result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                              capture_output=True, text=True, timeout=5)
                        process_still_running = str(pid) in result.stdout
                    else:
                        os.kill(pid, 0)
                        process_still_running = True
                except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                    process_still_running = False
                
                if process_still_running:
                    print(f"Process {pid} did not stop gracefully. Attempting forced termination...")
                    try:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                                         check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            os.kill(pid, signal.SIGKILL)
                        time.sleep(1.0)
                        print(f"Process {pid} forcefully terminated.")
                    except Exception as force_error:
                        print(f"Failed to forcefully terminate process {pid}: {force_error}")
                        return 1
                else:
                    print(f"Process {pid} stopped successfully.")
                
                # Clean up PID file
                try:
                    if os.path.exists(pid_file_path):
                        os.remove(pid_file_path)
                        print("PID file removed.")
                    else:
                        print("PID file already removed by process.")
                except OSError as remove_error:
                    print(f"Warning: Could not remove PID file: {remove_error}")
                
                return 0
                
            except subprocess.CalledProcessError as kill_error:
                print(f"Failed to terminate process {pid}: {kill_error}")
                return 1
            except OSError as os_error:
                if hasattr(os_error, 'errno') and os_error.errno == errno.ESRCH:
                    print(f"Process {pid} no longer exists. Removing stale PID file.")
                    os.remove(pid_file_path)
                    return 0
                else:
                    print(f"Error terminating process {pid}: {os_error}")
                    return 1
                    
    except ValueError as value_error:
        print(f"Invalid PID in file: {value_error}. Removing corrupt PID file.")
        try:
            os.remove(pid_file_path)
        except OSError:
            pass
        return 1
    except IOError as io_error:
        print(f"Error reading PID file: {io_error}")
        return 1

def main() -> int:
    """Main application entry point."""
    PID_FILE_PATH = os.path.join(tempfile.gettempdir(), "threethreeter_silent.pid")

    parser = argparse.ArgumentParser(description='Threethreeter Process Manager')
    parser.add_argument('--skip-checks', action='store_true',
                       help='Skip system requirement checks')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('-s', '--silent', action='store_true',
                       help='Run in silent mode (no UI, background process)')
    parser.add_argument('-i', '--info', action='store_true',
                       help='Show current status information and exit')
    parser.add_argument('command', nargs='?', choices=['stop'],
                       help='Command to execute (stop: terminate running silent process)')
    args = parser.parse_args()

    # Handle stop command first, before any other setup
    if args.command == 'stop':
        return stop_silent_process(PID_FILE_PATH)

    # Handle info flag first, before any other setup
    if args.info:
        print_status_info()
        return 0

    # Configure logging level based on args
    if args.debug:
        config.set("logging", "level", value="DEBUG")

    # Initial PID check for existing silent process (must happen before daemonization)
    if args.silent and os.path.exists(PID_FILE_PATH):
        try:
            pid_to_kill = -1
            with open(PID_FILE_PATH, "r") as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid_to_kill = int(pid_str)
                    module_logger.info(f"Existing silent mode PID file found: {PID_FILE_PATH} with PID {pid_to_kill}. Attempting to stop process.")
                else:
                    module_logger.warning(f"PID file {PID_FILE_PATH} was empty. Removing.")
                    os.remove(PID_FILE_PATH)
                    pid_to_kill = -1
        except ValueError as e_val:
            module_logger.error(f"PID file {PID_FILE_PATH} contained invalid data: {e_val}. Removing.")
            try:
                os.remove(PID_FILE_PATH)
            except OSError as e_os:
                module_logger.error(f"Error removing corrupt PID file {PID_FILE_PATH}: {e_os}")
            pid_to_kill = -1
        except IOError as e_io:
            module_logger.error(f"Error reading PID file {PID_FILE_PATH}: {e_io}. Cannot determine if existing process is running.")
            # Depending on policy, we might exit or try to continue. For now, assume we try to continue.
            pid_to_kill = -1

        if pid_to_kill != -1:
            try:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(pid_to_kill), '/F'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    module_logger.info(f"Termination signal sent to existing process {pid_to_kill} (Windows).")
                    print(f"Termination signal sent to existing process {pid_to_kill} (Windows).", file=sys.stdout)
                else:
                    os.kill(pid_to_kill, signal.SIGTERM)
                    module_logger.info(f"Termination signal sent to existing process {pid_to_kill} (Unix).")
                    print(f"Termination signal sent to existing process {pid_to_kill} (Unix).", file=sys.stdout)
                
                module_logger.info(f"Successfully terminated existing silent process {pid_to_kill}.")
                try:
                    os.remove(PID_FILE_PATH)
                    module_logger.info(f"PID file {PID_FILE_PATH} removed after stopping process {pid_to_kill}.")
                except OSError as e_rem_pid:
                    module_logger.warning(f"Could not remove PID file {PID_FILE_PATH} after signaling process {pid_to_kill}: {e_rem_pid}. It might have been removed by the process itself.")
                
                # Wait for the process to fully terminate before continuing
                print("Waiting for previous process to fully stop...", file=sys.stdout)
                time.sleep(2.0)  # Give the previous process time to clean up
                module_logger.info("Continuing with new silent process startup after stopping existing process.")
                
            except ProcessLookupError:
                module_logger.warning(f"Existing silent process {pid_to_kill} not found or already stopped. Removing stale PID file.")
                print(f"Existing process with PID {pid_to_kill} not found. Removing stale PID file.", file=sys.stdout)
                try:
                    os.remove(PID_FILE_PATH)
                    module_logger.info(f"Stale PID file {PID_FILE_PATH} removed for non-existent process {pid_to_kill}.")
                except OSError as e_rem_stale:
                    module_logger.error(f"Error removing stale PID file {PID_FILE_PATH} for process {pid_to_kill}: {e_rem_stale}")
            except subprocess.CalledProcessError as e_taskkill:
                module_logger.error(f"Failed to kill existing Windows process {pid_to_kill} with taskkill: {e_taskkill}. Removing stale PID file.")
                print(f"Failed to kill existing Windows process with PID {pid_to_kill}. Removing stale PID file.", file=sys.stdout)
                try:
                    os.remove(PID_FILE_PATH)
                    module_logger.info(f"Stale PID file {PID_FILE_PATH} removed after taskkill failure for process {pid_to_kill}.")
                except OSError as e_rem_taskkill_fail:
                    module_logger.error(f"Error removing stale PID file {PID_FILE_PATH} for process {pid_to_kill} after taskkill failure: {e_rem_taskkill_fail}")
            except OSError as e_kill:
                module_logger.error(f"Failed to terminate process {pid_to_kill}: {e_kill}. Stale PID file may remain.")
                print(f"Error killing existing process with PID {pid_to_kill}: {e_kill}. Stale PID file may remain.", file=sys.stdout)
                if hasattr(e_kill, 'errno') and e_kill.errno == errno.ESRCH: # No such process
                     try:
                        os.remove(PID_FILE_PATH)
                        module_logger.info(f"Stale PID file {PID_FILE_PATH} removed for process {pid_to_kill} (ESRCH).")
                     except OSError as e_rem_esrch:
                        module_logger.error(f"Error removing stale PID file {PID_FILE_PATH} for process {pid_to_kill} after ESRCH: {e_rem_esrch}")

            # Remove the exit here - continue with normal startup
            module_logger.info("Previous silent process stopped. Continuing with new silent mode startup.")
            print("Previous silent process stopped. Starting new silent process...", file=sys.stdout)

    # Logging setup should happen after the initial PID check for silent mode,
    # but before daemonization for POSIX so daemon can log.
    setup_logging()

    if args.silent:
        module_logger.info("Silent mode requested. Preparing environment...")
    else:
        # If not starting in silent mode, and a PID file exists, it might be from a previous crashed/unclean silent run.
        if os.path.exists(PID_FILE_PATH):
            module_logger.warning(f"PID file {PID_FILE_PATH} found while starting in interactive mode. This might be from an old session. Removing it.")
            try:
                os.remove(PID_FILE_PATH)
            except OSError as e:
                module_logger.error(f"Could not remove old PID file {PID_FILE_PATH}: {e}")
        module_logger.info("Running in interactive mode.")
        module_logger.info("Threethreeter Process Manager starting in interactive mode...")

    # Perform system checks BEFORE starting services to avoid multi-threading fork issues
    if not args.skip_checks:
        if args.silent:
            # In silent mode, perform checks but suppress output to avoid interfering with daemon
            module_logger.info("Performing system checks in silent mode...")
            try:
                # Import and run system check silently
                from .system_check import check_system_requirements_silent
                if not check_system_requirements_silent():
                    module_logger.error("System check failed in silent mode. Check logs for details.")
                    return 1
                module_logger.info("System checks passed in silent mode.")
            except ImportError:
                # Fallback to regular system check but redirect output
                import io
                import contextlib
                
                # Capture stdout to suppress system check output in silent mode
                stdout_capture = io.StringIO()
                with contextlib.redirect_stdout(stdout_capture):
                    check_result = print_system_status()
                
                if not check_result:
                    module_logger.error("System check failed in silent mode. Please fix the issues and try again.")
                    return 1
                module_logger.info("System checks completed in silent mode.")
        else:
            # Interactive mode - show full system check output
            if not print_system_status():
                module_logger.error("System check failed. Please fix the issues above.")
                return 1

    process_manager = None
    terminal_ui = None
    try:
        process_manager = setup_environment()
        if not process_manager:
            module_logger.error("Failed to setup environment. Exiting.")
            return 1
        
        module_logger.info("Environment setup complete.")

        # Start services after system checks but before forking for silent mode
        try:
            process_manager.start_all_services()
            module_logger.info("All services started successfully.")
        except Exception as service_error:
            module_logger.error(f"Error starting services: {service_error}", exc_info=True)
            return 1

        if args.silent:
            if os.name == 'posix':
                module_logger.info("POSIX system detected. Proceeding with daemonization...")
                # Double fork for daemonization
                try:
                    pid = os.fork()
                    if pid > 0: # Parent of first fork
                        module_logger.info(f"First fork parent exiting (PID: {os.getpid()}). Child PID: {pid}")
                        sys.exit(0)
                except OSError as e:
                    module_logger.error(f"Daemonization: First fork failed: {e}", exc_info=True)
                    sys.exit(1)
                
                # Child of first fork continues
                module_logger.info(f"Daemonization: Child of first fork (PID {os.getpid()}) continuing.")
                os.setsid() # Create new session and detach from controlling terminal
                os.umask(0) # Set umask to 0 to control file permissions directly
                module_logger.info(f"Daemonization: Child of first fork (PID: {os.getpid()}) became session leader.")

                try:
                    pid = os.fork()
                    if pid > 0: # Parent of second fork
                        module_logger.info(f"Daemonization: Second fork parent exiting (PID: {os.getpid()}). Daemon PID: {pid}")
                        sys.exit(0)
                except OSError as e:
                    module_logger.error(f"Daemonization: Second fork failed: {e}", exc_info=True)
                    sys.exit(1)

                # Grandchild (daemon) continues
                module_logger.info(f"Daemonization: Daemon process (PID: {os.getpid()}) started. Redirecting stdio.")

                # Redirect standard file descriptors
                sys.stdout.flush()
                sys.stderr.flush()
                si = open(os.devnull, 'r')
                so = open(os.devnull, 'a+') # Use /var/log/appname.out or similar in production
                se = open(os.devnull, 'a+') # Use /var/log/appname.err or similar in production
                os.dup2(si.fileno(), sys.stdin.fileno())
                os.dup2(so.fileno(), sys.stdout.fileno())
                os.dup2(se.fileno(), sys.stderr.fileno())
                module_logger.info("Standard file descriptors redirected to /dev/null.")

            else: # Not POSIX (e.g., Windows)
                module_logger.info("Non-POSIX system. Running in background without forking (standard silent mode).")

            # Write PID file *after* daemonization (for POSIX) or after services started (Windows)
            try:
                current_pid = os.getpid()
                with open(PID_FILE_PATH, "w") as f:
                    f.write(str(current_pid))
                # Log for Silent Mode Activation and PID File Creation
                module_logger.info(f"Silent mode activated. PID file {PID_FILE_PATH} created for silent mode process {current_pid}.")
            except IOError as e_io_write:
                # Log for Errors in PID File Writing
                module_logger.critical(f"CRITICAL: Failed to write PID file {PID_FILE_PATH} for PID {current_pid}: {e_io_write}.", exc_info=True)
                print(f"CRITICAL: Failed to write PID to {PID_FILE_PATH}: {e_io_write}. Silent mode cannot start reliably.", file=sys.stderr)
                if process_manager:
                    process_manager.stop_all()
                sys.exit(1)
            
            # Main loop for silent mode
            module_logger.info(f"Silent mode daemon (PID: {current_pid}) entering main loop. Waiting for signals...")
            try:
                while True:
                    signal.pause()
            except KeyboardInterrupt:
                module_logger.info("Silent mode interrupted by SIGINT (Ctrl+C). Shutting down...")
            except SystemExit as se:
                module_logger.info(f"Silent mode received SystemExit({se.code}). Shutting down...")
            # SIGTERM is handled by the signal handler which raises SystemExit.
            
        else: # Not args.silent (interactive mode)
            terminal_ui = TerminalUI(process_manager)
            module_logger.info("Starting Terminal UI...")
            try:
                curses.wrapper(terminal_ui.run)
            except Exception as ui_error:
                # Ensure curses is cleaned up *before* printing, if possible
                try:
                    curses.endwin() # End curses window if UI was running
                except Exception: # Catch all curses errors, e.g. endwin called repeatedly
                    pass # Ignore errors here, main error is ui_error

                # Print directly to stderr, bypassing logging for this specific case
                module_logger.error(f"Terminal UI Crashed: {ui_error}", exc_info=True) # Log the full error
                # Also print a simpler message to stderr for quick visibility
                print(f"\n--- Terminal UI Crashed: {type(ui_error).__name__}: {ui_error} ---", file=sys.stderr)
                print("--- See logs for full traceback. ---", file=sys.stderr)
                return 1 # Exit with error code

    except KeyboardInterrupt:
        module_logger.info("Shutdown requested by user (KeyboardInterrupt)...")
    except SystemExit as e: # Catch SystemExit to allow clean exit from signal handlers
        if e.code == 0:
             module_logger.info(f"Application exiting normally (SystemExit code 0).")
        else:
             module_logger.warning(f"Application exiting with error code {e.code} (SystemExit).")
        # The finally block will handle cleanup. Re-raise if necessary or return e.code
        # For this structure, let finally do its job and then the script will exit with e.code
        if process_manager: # Ensure services are stopped if exit happens early
            process_manager.stop_all()
        # PID file should be handled by finally or signal handler's exit path
        if e.code != 0:
            return e.code # Propagate error code
        return 0 # For sys.exit(0)
    except Exception as e:
        # Catch any other unhandled errors during setup or initial checks
        try:
            curses.endwin()
        except:
            pass
        print("\n--- Unhandled Error During Setup ---", file=sys.stderr)
        print(f"Error Type: {type(e).__name__}", file=sys.stderr)
        print(f"Error Details: {e}", file=sys.stderr)
        print("\n--- Traceback ---", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("--- End Traceback ---", file=sys.stderr)
        try:
            module_logger.error(f"Unhandled error during setup: {e}", exc_info=True)
        except Exception as log_err:
            print(f"\n*** Error occurred while trying to log setup error: {log_err} ***", file=sys.stderr)

        return 1
    finally:
        # Ensure curses is ended if it was started and we are not in silent mode
        if 'args' in locals() and hasattr(args, 'silent') and not args.silent and terminal_ui is not None:
            try:
                curses.endwin()
            except curses.error as e_curses: # More specific catch for curses errors
                if "endwin() called repeatedly" not in str(e_curses):
                    module_logger.debug(f"Curses endwin error during finally: {e_curses}")
            except Exception as e_generic_curses: # Catch any other potential error during curses cleanup
                 module_logger.debug(f"Generic error during curses endwin in finally: {e_generic_curses}")

        if process_manager:
            module_logger.info("Initiating service shutdown in finally block...")
            process_manager.stop_all()
        else:
            module_logger.info("Process manager not initialized, skipping service shutdown in finally block.")

        # PID file removal for silent mode.
        # This needs to be robust, especially for the daemon.
        # 'args' might not be defined if error occurs before arg parsing (unlikely here but good practice)
        if 'args' in locals() and hasattr(args, 'silent') and args.silent:
            # Only the actual daemon process should remove the PID file on exit.
            # Parent processes of forks will have already exited.
            # Check if the current PID matches the one in the file.
            current_pid_at_exit = os.getpid()
            pid_in_file = -1
            pid_file_still_exists = os.path.exists(PID_FILE_PATH)

            if pid_file_still_exists:
                try:
                    with open(PID_FILE_PATH, "r") as f:
                        content = f.read().strip()
                        if content:
                            pid_in_file = int(content)
                except (IOError, ValueError) as e_read_pid:
                    module_logger.error(f"Error reading PID from {PID_FILE_PATH} during shutdown: {e_read_pid}")
            
            if pid_file_still_exists and pid_in_file == current_pid_at_exit:
                try:
                    os.remove(PID_FILE_PATH)
                    module_logger.info(f"PID file {PID_FILE_PATH} removed by process {current_pid_at_exit} during shutdown.")
                except OSError as e_remove:
                    module_logger.error(f"Error removing PID file {PID_FILE_PATH} during shutdown by process {current_pid_at_exit}: {e_remove}")
            elif pid_file_still_exists:
                module_logger.info(f"Shutdown: PID in {PID_FILE_PATH} ({pid_in_file}) does not match current PID ({current_pid_at_exit}). PID file not removed by this process.")

        module_logger.info("Application shutdown sequence in finally block complete.")

    return 0 # Default exit code for successful completion

if __name__ == "__main__":
    # Define a global signal handler for SIGTERM to ensure cleanup, especially for silent mode
    # This helps in cases where SIGTERM is received directly by the process.
    def handle_sigterm(signum, frame):
        # Check if module_logger is available (it should be by the time signals are handled)
        if 'module_logger' in globals() and module_logger:
            module_logger.info(f"Received signal {signal.Signals(signum).name}. Initiating graceful shutdown...")
        else: # Fallback if logger isn't set up
            print(f"Received signal {signal.Signals(signum).name}. Initiating graceful shutdown...", file=sys.stderr)
        
        # Raising SystemExit(0) is a clean way to trigger the finally block and exit gracefully.
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    # SIGINT is usually handled by KeyboardInterrupt, but for daemons, explicit handling might be desired.
    # If ProcessManager or other parts handle SIGINT and stop services, that's often enough.
    # If we want SIGINT to also trigger this handler for the daemon:
    # signal.signal(signal.SIGINT, handle_sigterm) 

    exit_code = main()
    # Ensure logger flushes if it has handlers
    if 'module_logger' in globals() and module_logger and module_logger.hasHandlers():
        for handler in module_logger.handlers:
            handler.flush()
    sys.exit(exit_code)
