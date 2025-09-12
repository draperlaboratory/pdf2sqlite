{
  inputs = {
    utils.url = "github:numtide/flake-utils";
  };

  outputs = { 
    self, 
    nixpkgs, 
    utils,
  }: utils.lib.eachDefaultSystem (system:
  let
    inherit (nixpkgs) lib;
    pkgs = nixpkgs.legacyPackages.${system};
    python = pkgs.python312;
    uvWrapped = pkgs.stdenv.mkDerivation {
      name = "uv-wrapped";
      nativeBuildInputs = [pkgs.makeWrapper];
      buildCommand = if pkgs.stdenv.isLinux then ''
      mkdir $out
      makeWrapper ${pkgs.uv}/bin/uv $out/bin/uv \
      --prefix UV_PYTHON_DOWNLOADS : "never" \
      --prefix UV_PYTHON : "${python.interpreter}" \
      --prefix LD_LIBRARY_PATH : "${lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1}" 
      '' else ''
      mkdir $out
      makeWrapper ${pkgs.uv}/bin/uv $out/bin/uv \
      --prefix UV_PYTHON_DOWNLOADS : "never" \
      --prefix UV_PYTHON : "${python.interpreter}" '';
    };
  in
  {

    devShell = with pkgs; mkShell {
      packages = [
        python
        uvWrapped
        awscli2
        sqlite
      ];
      shellHook = ''
      unset PYTHONPATH
      SHELL=${pkgs.bashInteractive}/bin/bash
      '';
    };
  });
}
