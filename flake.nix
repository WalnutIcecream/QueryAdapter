{
  description = "QueryAdapter — natural-language querying for SQL, NoSQL, and graph databases";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
      in {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            python311
            python311Packages.pip
            python311Packages.virtualenv
            ollama
            sqlite
            jq
            git
            curl
          ];

          shellHook = ''
            echo "QueryAdapter development environment"

            if [ ! -d .venv ]; then
              python -m venv .venv
            fi

            source .venv/bin/activate
            pip install --upgrade pip
            pip install -e ".[test]"
          '';
        };
      });
}
