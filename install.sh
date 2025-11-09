#!/usr/bin/env bash
# Markdown Web Browser - All-in-One Installer Script
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/yourusername/markdown_web_browser/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/yourusername/markdown_web_browser/main/install.sh | bash -s -- --yes
#   wget -qO- https://raw.githubusercontent.com/yourusername/markdown_web_browser/main/install.sh | bash
#
# Options:
#   --yes, -y              Skip all confirmations (non-interactive mode)
#   --dir=PATH            Installation directory (default: ./markdown_web_browser)
#   --no-deps             Skip system dependency installation
#   --no-browsers         Skip Playwright browser installation
#   --ocr-key=KEY         Set OCR API key directly
#   --help, -h            Show this help message

set -euo pipefail

# Configuration
REPO_URL="${MDWB_REPO_URL:-https://github.com/anthropics/markdown_web_browser.git}"
DEFAULT_INSTALL_DIR="./markdown_web_browser"
PYTHON_VERSION="${MDWB_PYTHON_VERSION:-3.13}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
INSTALL_DIR="$DEFAULT_INSTALL_DIR"
SKIP_CONFIRM=false
INSTALL_DEPS=true
INSTALL_BROWSERS=true
OCR_API_KEY=""

# Function to print colored output
print_color() {
    local color=$1
    shift
    echo -e "${color}$@${NC}"
}

# Function to print usage
usage() {
    cat << EOF
Markdown Web Browser - All-in-One Installer

Usage: $0 [OPTIONS]

Options:
    --yes, -y              Skip all confirmations (non-interactive mode)
    --dir=PATH            Installation directory (default: $DEFAULT_INSTALL_DIR)
    --no-deps             Skip system dependency installation
    --no-browsers         Skip Playwright browser installation
    --ocr-key=KEY         Set OCR API key directly
    --help, -h            Show this help message

Examples:
    # Interactive installation
    $0

    # Non-interactive with all defaults
    $0 --yes

    # Custom directory with OCR key
    $0 --dir=/opt/mdwb --ocr-key=sk-YOUR-KEY

    # Skip browser installation (useful for headless servers)
    $0 --no-browsers

EOF
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y)
            SKIP_CONFIRM=true
            shift
            ;;
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --dir=*)
            INSTALL_DIR="${1#*=}"
            shift
            ;;
        --no-deps)
            INSTALL_DEPS=false
            shift
            ;;
        --no-browsers)
            INSTALL_BROWSERS=false
            shift
            ;;
        --ocr-key)
            OCR_API_KEY="$2"
            shift 2
            ;;
        --ocr-key=*)
            OCR_API_KEY="${1#*=}"
            shift
            ;;
        --help|-h)
            usage
            ;;
        *)
            print_color "$RED" "Unknown option: $1"
            usage
            ;;
    esac
done

# Function to check if command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Function to detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command_exists apt-get; then
            echo "debian"
        elif command_exists yum; then
            echo "redhat"
        elif command_exists pacman; then
            echo "arch"
        else
            echo "unknown"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

# Function to install uv
install_uv() {
    if command_exists uv; then
        print_color "$GREEN" "✓ uv is already installed"
        return 0
    fi

    print_color "$BLUE" "Installing uv package manager..."

    if command_exists curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command_exists wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        print_color "$RED" "Error: Neither curl nor wget found. Please install one of them first."
        exit 1
    fi

    # Add uv to PATH for current session
    export PATH="$HOME/.cargo/bin:$PATH"

    if command_exists uv; then
        print_color "$GREEN" "✓ uv installed successfully"
    else
        print_color "$RED" "Error: uv installation failed"
        exit 1
    fi
}

# Function to install system dependencies
install_system_deps() {
    if [ "$INSTALL_DEPS" = false ]; then
        print_color "$YELLOW" "Skipping system dependency installation"
        return 0
    fi

    local os_type=$(detect_os)

    print_color "$BLUE" "Installing system dependencies for $os_type..."

    case $os_type in
        debian)
            if [ "$SKIP_CONFIRM" = false ]; then
                read -p "Install system dependencies (libvips-dev, git)? [Y/n] " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]] && [ ! -z "$REPLY" ]; then
                    print_color "$YELLOW" "Skipping system dependencies"
                    return 0
                fi
            fi

            print_color "$BLUE" "Installing libvips and other dependencies..."
            sudo apt-get update
            sudo apt-get install -y libvips-dev git
            ;;

        macos)
            if ! command_exists brew; then
                print_color "$RED" "Homebrew is required on macOS. Please install it first:"
                print_color "$YELLOW" "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                exit 1
            fi

            print_color "$BLUE" "Installing libvips via Homebrew..."
            brew install vips
            ;;

        redhat)
            print_color "$BLUE" "Installing libvips on RedHat-based system..."
            sudo yum install -y vips-devel git
            ;;

        arch)
            print_color "$BLUE" "Installing libvips on Arch Linux..."
            sudo pacman -S --noconfirm libvips git
            ;;

        *)
            print_color "$YELLOW" "Unknown OS. Please install libvips manually:"
            print_color "$YELLOW" "  Ubuntu/Debian: sudo apt-get install libvips-dev"
            print_color "$YELLOW" "  macOS: brew install vips"
            print_color "$YELLOW" "  RedHat/CentOS: sudo yum install vips-devel"
            print_color "$YELLOW" "  Arch Linux: sudo pacman -S libvips"

            if [ "$SKIP_CONFIRM" = false ]; then
                read -p "Continue anyway? [y/N] " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    exit 1
                fi
            fi
            ;;
    esac

    print_color "$GREEN" "✓ System dependencies installed"
}

# Function to clone or update repository
setup_repository() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        print_color "$BLUE" "Updating existing repository..."
        cd "$INSTALL_DIR"
        git pull origin main
    else
        if [ -d "$INSTALL_DIR" ]; then
            if [ "$SKIP_CONFIRM" = false ]; then
                read -p "Directory $INSTALL_DIR exists. Remove and reinstall? [y/N] " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    print_color "$YELLOW" "Installation cancelled"
                    exit 1
                fi
            fi
            rm -rf "$INSTALL_DIR"
        fi

        print_color "$BLUE" "Cloning repository..."
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    print_color "$GREEN" "✓ Repository ready"
}

# Function to setup Python environment
setup_python_env() {
    print_color "$BLUE" "Setting up Python environment..."

    # Install Python if needed
    uv python install $PYTHON_VERSION

    # Create virtual environment
    if [ ! -d ".venv" ]; then
        uv venv --python $PYTHON_VERSION
    fi

    # Sync dependencies
    print_color "$BLUE" "Installing Python dependencies..."
    uv sync

    print_color "$GREEN" "✓ Python environment ready"
}

# Function to install Playwright browsers
install_playwright_browsers() {
    if [ "$INSTALL_BROWSERS" = false ]; then
        print_color "$YELLOW" "Skipping Playwright browser installation"
        return 0
    fi

    print_color "$BLUE" "Installing Playwright browsers..."

    uv run playwright install chromium
    uv run playwright install-deps chromium

    print_color "$GREEN" "✓ Playwright browsers installed"
}

# Function to setup configuration
setup_config() {
    print_color "$BLUE" "Setting up configuration..."

    # Copy example env file if it doesn't exist
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_color "$GREEN" "✓ Created .env from .env.example"
        else
            print_color "$YELLOW" "Warning: No .env.example found"
        fi
    else
        print_color "$GREEN" "✓ .env file already exists"
    fi

    # Set OCR API key if provided
    if [ ! -z "$OCR_API_KEY" ]; then
        if grep -q "^OLMOCR_API_KEY=" .env; then
            sed -i.bak "s/^OLMOCR_API_KEY=.*/OLMOCR_API_KEY=$OCR_API_KEY/" .env
            rm .env.bak
            print_color "$GREEN" "✓ OCR API key configured"
        else
            echo "OLMOCR_API_KEY=$OCR_API_KEY" >> .env
            print_color "$GREEN" "✓ OCR API key added to .env"
        fi
    else
        print_color "$YELLOW" "Note: OCR API key not configured. You can add it later to .env"
    fi
}

# Function to run tests
run_tests() {
    print_color "$BLUE" "Running basic tests..."

    # Test pyvips import
    if uv run python -c "import pyvips; print('✓ pyvips works')" 2>/dev/null; then
        print_color "$GREEN" "✓ pyvips import successful"
    else
        print_color "$RED" "✗ pyvips import failed - libvips may not be installed correctly"
        return 1
    fi

    # Test Playwright
    if [ "$INSTALL_BROWSERS" = true ]; then
        if uv run python -c "from playwright.async_api import async_playwright; print('✓ Playwright works')" 2>/dev/null; then
            print_color "$GREEN" "✓ Playwright import successful"
        else
            print_color "$RED" "✗ Playwright import failed"
            return 1
        fi
    fi

    # Test CLI
    if uv run python -m scripts.mdwb_cli --help > /dev/null 2>&1; then
        print_color "$GREEN" "✓ CLI tool works"
    else
        print_color "$RED" "✗ CLI tool failed"
        return 1
    fi

    return 0
}

# Function to create launcher script
create_launcher() {
    local launcher_path="$INSTALL_DIR/mdwb"

    cat > "$launcher_path" << 'EOF'
#!/usr/bin/env bash
# Markdown Web Browser CLI Launcher

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Ensure we're using the virtual environment
exec uv run python -m scripts.mdwb_cli "$@"
EOF

    chmod +x "$launcher_path"

    print_color "$GREEN" "✓ Created launcher script: $launcher_path"
    print_color "$YELLOW" "  You can add it to your PATH or create an alias:"
    print_color "$YELLOW" "  alias mdwb='$launcher_path'"
}

# Main installation flow
main() {
    print_color "$BLUE" "════════════════════════════════════════════════"
    print_color "$BLUE" "   Markdown Web Browser - All-in-One Installer  "
    print_color "$BLUE" "════════════════════════════════════════════════"
    echo

    # Show installation plan
    print_color "$YELLOW" "Installation Plan:"
    print_color "$YELLOW" "  • Install directory: $INSTALL_DIR"
    print_color "$YELLOW" "  • Python version: $PYTHON_VERSION"
    print_color "$YELLOW" "  • Install system deps: $INSTALL_DEPS"
    print_color "$YELLOW" "  • Install browsers: $INSTALL_BROWSERS"

    if [ ! -z "$OCR_API_KEY" ]; then
        print_color "$YELLOW" "  • OCR API key: ${OCR_API_KEY:0:10}..."
    fi
    echo

    # Confirm installation
    if [ "$SKIP_CONFIRM" = false ]; then
        read -p "Proceed with installation? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]] && [ ! -z "$REPLY" ]; then
            print_color "$YELLOW" "Installation cancelled"
            exit 0
        fi
    fi

    # Create installation directory
    mkdir -p "$(dirname "$INSTALL_DIR")"

    # Run installation steps
    install_uv
    install_system_deps
    setup_repository
    setup_python_env
    install_playwright_browsers
    setup_config

    # Run tests
    if run_tests; then
        print_color "$GREEN" "✓ All tests passed"
    else
        print_color "$YELLOW" "⚠ Some tests failed, but installation completed"
    fi

    # Create launcher
    create_launcher

    # Print success message
    echo
    print_color "$GREEN" "════════════════════════════════════════════════"
    print_color "$GREEN" "   Installation Complete!                       "
    print_color "$GREEN" "════════════════════════════════════════════════"
    echo
    print_color "$BLUE" "Quick Start:"
    print_color "$BLUE" "  cd $INSTALL_DIR"
    print_color "$BLUE" "  uv run python -m scripts.mdwb_cli fetch https://example.com"
    echo
    print_color "$BLUE" "Or use the launcher:"
    print_color "$BLUE" "  $INSTALL_DIR/mdwb fetch https://example.com"
    echo

    if [ -z "$OCR_API_KEY" ]; then
        print_color "$YELLOW" "Don't forget to add your OCR API key to $INSTALL_DIR/.env"
        print_color "$YELLOW" "  OLMOCR_API_KEY=your-api-key-here"
    fi

    echo
    print_color "$GREEN" "Happy browsing! 🎉"
}

# Run main function
main