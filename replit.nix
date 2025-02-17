{pkgs}: {
  deps = [
    pkgs.python311Packages.ipython
    pkgs.redis
    pkgs.libyaml
    pkgs.fontconfig
    pkgs.libxcrypt
  ];
}
