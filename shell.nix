# shell.nix
{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python313;
  pyPkgs = python.pkgs;
in
pkgs.mkShell {
  name = "python-dev-tools";

  packages = with pkgs; [
    python313 

    # Python packages
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
    pyPkgs.jsonschema-specifications
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

    ruff

    # Pyright language server/CLI (Node-based)
    nodejs_20
    pyright

    vscode
  ];
}
