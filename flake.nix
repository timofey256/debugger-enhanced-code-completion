{
  description = "Dev shell pinned to nixos-unstable";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    openspec.url = "github:Fission-AI/OpenSpec";
    swebench-src = {
      url = "github:SWE-bench/SWE-bench/fa79f3af3e0f212d4d14b1c858c77fcaae5308ce";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, openspec, swebench-src }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      config.allowUnfree = true;
    };

    swebench = pkgs.applyPatches {
      name = "swebench-patched";
      src = swebench-src;
      patches = [ ./nix/swebench-remove-modal.patch ];
    };

    pythonEnv = pkgs.python313.withPackages (ps: [
      ps.docker
      ps.pytest
      ps.pytest-cov
      ps.rich
      ps.beautifulsoup4
      ps.chardet
      ps.ghapi
      ps.unidiff
      ps.datasets
      ps.python-dotenv
      ps.gitpython
      ps.pre-commit-hooks
      ps.requests
      ps.tenacity
      ps.tqdm
      ps.openai
      ps.pyyaml
    ]);

    docs = pkgs.runCommand "debugger-doxygen-docs"
      {
        nativeBuildInputs = [ pkgs.doxygen pkgs.graphviz ];
        src = self;
      }
      ''
        cd $src
        mkdir -p $out
        ( cat Doxyfile; echo "OUTPUT_DIRECTORY = $out" ) | doxygen -
      '';
  in
  {
    packages.${system}.docs = docs;

    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [
        pythonEnv

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
        export SWE_BENCH_PATH=${swebench}

        echo "NOTE: supply your API keys in the .env file in the project root (copy .env.example and fill in the values)."
      '';
    };
  };
}
