{
  description = "NLP to SQL Project";

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

            # Python
            python311
            python311Packages.pip
            python311Packages.virtualenv
            ollama
            # Database
            postgresql

            # Useful CLI tools
            jq
            yq
            sqlite

            # Development
            git
            curl

          ];

          shellHook = ''
            echo "NLP → SQL Development Environment"

            if [ ! -d .venv ]; then
              python -m venv .venv
            fi

            source .venv/bin/activate

            pip install --upgrade pip

            pip install \
              fastapi \
              uvicorn \
              sqlalchemy \
              psycopg2-binary \
              pydantic \
              pandas \
              streamlit \
              ollama \
              pyyaml \
              rich \
              python-dotenv
          '';
        };
      });
}
