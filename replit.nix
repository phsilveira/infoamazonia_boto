{pkgs}: {
  deps = [
    pkgs.glibc
    pkgs.gcc
    pkgs.sqlite-interactive
    pkgs.postgresql
    pkgs.python311Packages.ipython
    pkgs.redis
    pkgs.libyaml
    pkgs.fontconfig
    pkgs.libxcrypt
  ];
}
