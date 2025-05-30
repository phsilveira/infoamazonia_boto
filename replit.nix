{pkgs}: {
  deps = [
    pkgs.pyenv
    pkgs.glibc
    pkgs.gcc
    pkgs.libstdcxx5
    pkgs.sqlite-interactive
    pkgs.postgresql
    pkgs.python311Packages.ipython
    pkgs.redis
    pkgs.libyaml
    pkgs.fontconfig
    pkgs.libxcrypt
  ];
}
