# Documentation: https://docs.brew.sh/Formula-Cookbook
#                https://rubydoc.brew.sh/Formula
class Threethreeter < Formula
  desc "Local backend for the 33ter OCR code solution app"
  homepage "https://github.com/designerGenes/33ter_backend"
  url "https://github.com/designerGenes/33ter_backend/archive/refs/tags/v0.1.1.tar.gz"
  sha256 "70cf1a9021200fd107416dbcfb8dfabb473f2913b263beea51a4b6ab57d08e0d"
  license "MIT"
  version "0.1.1"

  depends_on "python@3.11"
  depends_on "tesseract"
  depends_on "tesseract-lang"

  def install
    # Homebrew unpacks the tarball into a temporary directory.
    # Let's see what's in the current directory (.) when install runs.
    ohai "Listing current directory contents during install:"
    system "ls", "-la", "."

    # Define the path to requirements.txt relative to the unpacked structure
    # Assuming the CWD contains the 'LocalBackend' directory from the tarball.
    requirements_path = Pathname.pwd/"LocalBackend/req/requirements.txt"

    # Check if requirements file exists before trying to install
    unless requirements_path.exist?
      odie "Requirements file not found at expected path: #{requirements_path}. Check tarball structure and directory listing above."
    end

    # Install dependencies directly into libexec using the Homebrew Python's pip
    python_bin = Formula["python@3.11"].opt_bin
    system python_bin/"pip3", "install", "--upgrade", "pip"
    # Install dependencies into the libexec prefix structure
    system python_bin/"pip3", "install", "-r", requirements_path, "--prefix=#{libexec}"

    # Construct the site-packages path within libexec
    site_packages = Language::Python.site_packages(Formula["python@3.11"].opt_bin/"python3")
    libexec_site_packages = libexec/site_packages.sub(Formula["python@3.11"].opt_prefix.to_s, "")

    # Copy the *contents* of the current directory (including LocalBackend) into libexec
    # This should result in libexec/LocalBackend/...
    libexec.install Dir["*"]

    # Create a wrapper script in bin, adjusting paths
    (bin/"33ter-backend").write <<~EOS
      #!/bin/bash
      # Add the LocalBackend source dir and libexec site-packages to PYTHONPATH
      export PYTHONPATH="#{libexec}/LocalBackend:#{libexec_site_packages}:$PYTHONPATH"
      exec "#{python_bin}/python3" "#{libexec}/LocalBackend/start_local_dev.py" "$@"
    EOS
  end

  def caveats
    <<~EOS
      The 33ter backend service can be started by running:
        33ter-backend

      Ensure Tesseract language data is correctly installed. You might need:
        brew install tesseract-lang
    EOS
  end

  test do
    assert_predicate bin/"33ter-backend", :exist?
    assert_predicate bin/"33ter-backend", :executable?
    # Test might involve checking if the script runs with a hypothetical --help flag
    # system bin/"33ter-backend", "--help"
  end
end
