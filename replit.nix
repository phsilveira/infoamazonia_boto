{pkgs}: {
  deps = [
    pkgs.postgresql
    pkgs.python311Packages.ipython
    pkgs.redis
    pkgs.libyaml
    pkgs.fontconfig
    pkgs.libxcrypt
  ];
}
