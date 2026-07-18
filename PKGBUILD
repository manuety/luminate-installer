# Maintainer: Arch User
pkgname=luminate-installer
pkgver=1.0.0
pkgrel=1
pkgdesc="Elegant package conversion and installation desktop utility"
arch=('any')
license=('GPL')
depends=('python' 'python-pywebview' 'webkit2gtk-4.1' 'debtap' 'yay')

package() {
  # Create destination directories
  install -d "${pkgdir}/usr/share/${pkgname}"
  install -d "${pkgdir}/usr/bin"
  install -d "${pkgdir}/usr/share/applications"
  install -d "${pkgdir}/usr/share/pixmaps"

  # Copy application files from startdir
  cp -r "${startdir}/static" "${pkgdir}/usr/share/${pkgname}/"
  install -m 644 "${startdir}/app.py" "${pkgdir}/usr/share/${pkgname}/"
  install -m 644 "${startdir}/main.py" "${pkgdir}/usr/share/${pkgname}/"

  # Create launcher script
  echo -e '#!/bin/sh\npython /usr/share/luminate-installer/main.py "$@"' > "${pkgdir}/usr/bin/${pkgname}"
  chmod +x "${pkgdir}/usr/bin/${pkgname}"

  # Install desktop file & icon
  install -m 644 "${startdir}/luminate-installer.desktop" "${pkgdir}/usr/share/applications/"
  install -m 644 "${startdir}/luminate-installer.svg" "${pkgdir}/usr/share/pixmaps/"
}
