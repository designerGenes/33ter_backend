# 33ter Process Manager

A terminal-based process manager for development workflows.

## System Requirements

- Python 3.8 or higher
- Linux, macOS, or Windows with WSL
- Basic terminal/shell access

## Quick Start

```bash
# Clone the repository
git clone [your-repo-url]
cd 33ter

# Start the application
./start.sh
```

## Features

- Multi-process management with real-time output monitoring
- Color-coded interface for different views
- Process status monitoring and control
- Automatic dependency management

## Command Line Options

```bash
./start.sh [options]

Options:
  --force-setup   Force recreation of virtual environment
  --skip-checks   Skip system requirement checks (use with caution)
```

## Troubleshooting

### Missing Dependencies
The application will attempt to install required Python packages automatically. However, some system-level dependencies might need manual installation:

#### Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install python3-tk python3-dev
```

#### Fedora:
```bash
sudo dnf install python3-tkinter python3-devel
```

#### Arch Linux:
```bash
sudo pacman -S tk python-pip
```

#### macOS:
```bash
brew install python-tk
```

### Common Issues

1. **pip not found**: The application will attempt to install pip automatically. If this fails, you can install it manually:
   ```bash
   curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
   python3 get-pip.py --user
   ```

2. **Permission Issues**: If you encounter permission errors:
   - Don't run the application with sudo
   - Ensure your user has write access to the application directory
   - Use `--user` flag for pip installations if needed

3. **Virtual Environment Issues**: If you encounter problems with the virtual environment:
   ```bash
   ./start.sh --force-setup
   ```

## Development Notes

- Process configurations are stored in `server_config.json`
- Each service (Screenshot, Process, Socket) runs in its own isolated environment
- Log files are stored in the `logs/` directory

## Development Setup

```bash
# Install dev dependencies
pip-sync [requirements-dev.txt](http://_vscodecontentref_/0)

# Install production dependencies only
pip-sync [requirements.txt](http://_vscodecontentref_/1)