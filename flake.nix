{
  description = "Dev shell pinned to nixos-unstable";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    openspec.url = "github:Fission-AI/OpenSpec";
  };

  outputs = { self, nixpkgs, openspec }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      config.allowUnfree = true;
    };
  in
  {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [
        pkgs.python313
        pkgs.python313Packages.docker
        pkgs.python313Packages.pytest
        pkgs.python313Packages.pytest-cov
        pkgs.python313Packages.rich
        pkgs.python313Packages.beautifulsoup4
        pkgs.python313Packages.chardet
        pkgs.python313Packages.ghapi
        pkgs.python313Packages.unidiff
        pkgs.python313Packages.unidiff
        pkgs.python313Packages.datasets
        pkgs.python313Packages.python-dotenv
        pkgs.python313Packages.gitpython
        pkgs.python313Packages.pre-commit-hooks
        pkgs.python313Packages.requests
        pkgs.python313Packages.tenacity
        pkgs.python313Packages.tqdm
        pkgs.python313Packages.openai
        pkgs.python313Packages.pyyaml

        pkgs.openssl
        pkgs.vscode
        pkgs.bash
        pkgs.nodejs_24
        pkgs.docker_29
        pkgs.tree

        pkgs.claude-code
        pkgs.codex
        pkgs.github-copilot-cli

        pkgs.doxygen
        pkgs.graphviz

        openspec.packages.${system}.default
      ];

      shellHook = ''
        export PYTHONPATH="$PWD:$PWD/libs:$PYTHONPATH"

        echo "Generating Doxygen documentation..."
        doxygen Doxyfile > /dev/null 2>&1
        echo "Doxygen documentation: output/doxygen/html/index.html"

        echo "NOTE: supply your API keys in the .env file in the project root (e.g. DEEPSEEK_API_KEY, OPENAI_API_KEY, CUSTOM_API_KEY)."
      '';
    };
  };
}
