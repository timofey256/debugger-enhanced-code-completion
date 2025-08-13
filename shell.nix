# shell.nix
{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312;
  pyPkgs = python.pkgs;
in
pkgs.mkShell {
  name = "python-dev-tools";

  packages = with pkgs; [
    python313 

    # Python packages
    python313Packages.pip
    python313Packages.black
    python313Packages.flake8
    python313Packages.isort
    python313Packages.mypy
    python313Packages.pytest
    python313Packages.requests
    python313Packages.attrs
    python313Packages.referencing
    python313Packages.jsonpointer
    python313Packages.jsonschema
    python313Packages.jsonschema-specifications
    python313Packages.jsonpath-ng
    python313Packages.arrow
    python313Packages.python-dateutil
    python313Packages.types-python-dateutil
    python313Packages.fqdn
    python313Packages.idna
    python313Packages.isoduration
    python313Packages.jsonschema-specifications
    python313Packages.rpds-py
    python313Packages.rfc3339-validator
    python313Packages.rfc3986-validator
    python313Packages.rfc3987
    python313Packages.uri-template
    python313Packages.webcolors
    python313Packages.six
    python313Packages.typing-extensions
    python313Packages.jsonpickle

    python313Packages.flask # for http backend

    ruff

    # Pyright language server/CLI (Node-based)
    nodejs_20
    pyright

    vscode
  ];
}
