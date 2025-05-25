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

try:
    # Use explicit relative imports since this script is inside the Threethreeter package
    from .system_check import print_system_status
    from .config_loader import config
    from .process_manager import ProcessManager
    from .terminal_ui import TerminalUI
except ImportError as e:
    print(f"Error importing required modules: {e}", file=sys.stderr)  # Print import errors to stderr
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
    logging.getLogger("socketio").setLevel(logging.ERROR)

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
    args = parser.parse_args()

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

            module_logger.info("Silent mode deactivation: Told existing process to stop. Exiting current invocation.")
            print("Silent mode deactivated (told existing process to stop). Exiting current invocation.", file=sys.stdout)
            sys.exit(0)

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


    process_manager = None
    try:
        if not args.skip_checks:
            if not print_system_status():
                module_logger.error("System check failed. Please fix the issues above.")
                return 1

        process_manager = setup_environment()
        if not process_manager:
            module_logger.error("Failed to setup environment. Exiting.")
            return 1
        
        module_logger.info("Environment setup complete.")

        # Start services before forking for silent mode, so child inherits them
        try:
            process_manager.start_all_services()
            module_logger.info("All services started successfully.")
        except Exception as service_error:
            module_logger.error(f"Error starting services: {service_error}", exc_info=True)
            # No PID file written yet in silent mode, so no cleanup needed here for that.
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
            except Exception as ui_error: # Catch more general exceptions from curses.wrapper
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
        # If exiting due to daemonization parent, this is fine.
        # If daemon is exiting via signal, finally block should catch it.
        # Re-raising to ensure the exit code is propagated if sys.exit() was called with a code
        # However, if it's from a sys.exit(0) in a parent fork, we don't want to return 1.
        # The main concern is that the finally block runs.
        # Let's assume sys.exit(0) is handled and does not result in return 1 here.
        # If e.code is not 0, it indicates an error.
        if e.code != 0:
            return e.code # Propagate error code
        return 0 # For sys.exit(0)
    except Exception as e:
        # Catch any other unhandled errors during setup or initial checks
        module_logger.critical(f"Unhandled error during execution: {e}", exc_info=True)
        # Also print a simpler message to stderr for quick visibility
        print(f"\n--- Unhandled Error: {type(e).__name__}: {e} ---", file=sys.stderr)
        print("--- See logs for full traceback. ---", file=sys.stderr)
        if not args.silent: # Try to clean up curses if UI might have been active
            try:
                curses.endwin()
            except:
                pass
        return 1
    finally:
        # Ensure curses is ended if it was started and we are not in silent mode
        if not args.silent and 'terminal_ui' in locals() and terminal_ui is not None:
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
        if 'args' in locals() and args.silent:
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
    # It's good practice to also import errno for some specific error checks if needed
    import errno # Keep this import here as it's used in main()

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
