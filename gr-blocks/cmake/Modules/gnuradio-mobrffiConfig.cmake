find_package(PkgConfig)

PKG_CHECK_MODULES(PC_GR_MOBRFFI gnuradio-mobrffi)

FIND_PATH(
    GR_MOBRFFI_INCLUDE_DIRS
    NAMES gnuradio/mobrffi/api.h
    HINTS $ENV{MOBRFFI_DIR}/include
        ${PC_MOBRFFI_INCLUDEDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/include
          /usr/local/include
          /usr/include
)

FIND_LIBRARY(
    GR_MOBRFFI_LIBRARIES
    NAMES gnuradio-mobrffi
    HINTS $ENV{MOBRFFI_DIR}/lib
        ${PC_MOBRFFI_LIBDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/lib
          ${CMAKE_INSTALL_PREFIX}/lib64
          /usr/local/lib
          /usr/local/lib64
          /usr/lib
          /usr/lib64
          )

include("${CMAKE_CURRENT_LIST_DIR}/gnuradio-mobrffiTarget.cmake")

INCLUDE(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(GR_MOBRFFI DEFAULT_MSG GR_MOBRFFI_LIBRARIES GR_MOBRFFI_INCLUDE_DIRS)
MARK_AS_ADVANCED(GR_MOBRFFI_LIBRARIES GR_MOBRFFI_INCLUDE_DIRS)
