{
  description = "Dev shell pinned to nixos-25.11";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };
  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
      config.allowUnfree = true;
    };
    python = pkgs.python313;
    pyPkgs = python.pkgs;
  in
  {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [
        # .NET and tools
        pkgs.dotnetCorePackages.dotnet_9.sdk
        pkgs.vscode
        pkgs.claude-code
        
        # Python and packages
        python
        pyPkgs.pip
        pyPkgs.black
        pyPkgs.flake8
        pyPkgs.isort
        pyPkgs.mypy
        pyPkgs.pytest
        pyPkgs.requests
        pyPkgs.attrs
        pyPkgs.referencing
        pyPkgs.jsonpointer
        pyPkgs.jsonschema
        pyPkgs.jsonschema-specifications
        pyPkgs.jsonpath-ng
        pyPkgs.arrow
        pyPkgs.python-dateutil
        pyPkgs.types-python-dateutil
        pyPkgs.fqdn
        pyPkgs.idna
        pyPkgs.isoduration
        pyPkgs.rpds-py
        pyPkgs.rfc3339-validator
        pyPkgs.rfc3986-validator
        pyPkgs.rfc3987
        pyPkgs.uri-template
        pyPkgs.webcolors
        pyPkgs.six
        pyPkgs.typing-extensions
        pyPkgs.jsonpickle
        pyPkgs.build
        pyPkgs.twine
        pyPkgs.flask
        pkgs.ruff
        
        # Node.js and Pyright
        pkgs.nodejs_20
        pkgs.pyright
      ];
      
      shellHook = ''
        export NIXPKGS_ALLOW_UNFREE=1
      '';
    };
  };
}
