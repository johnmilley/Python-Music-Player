- replace any horizontal scroll with the same custom scrollbar as the vertical. but as with everything else, make sure to square it, do away with roundness.

- hearts have accent color. great. it disappears when that song is playing bc its same color as highlight. maybe convert to black in that case. open to suggestions there.

- when i load app in dark mode there is weird behavior in main mode where the filebrowswer is black (where text is) but everything else is white.

- opacity option for overlay is good. also add that to the whole player. i'd just like to see how it looks.

  
- error to deal with. been noticing a bit of hanging in general when quickly switching albums/songs. let's do a performance audit and make sure our app is the best it can be.  when done, commit, new builds, and replace current local binary with updated one.
```
           PID: 9649 (python3)
           UID: 1000 (johnathan)
           GID: 1000 (johnathan)
        Signal: 6 (ABRT)
     Timestamp: Mon 2026-07-13 09:06:26 NDT (5s ago)
  Command Line: python3 src/app.py
    Executable: /usr/bin/python3.14
 Control Group: /user.slice/user-1000.slice/user@1000.service/app.slice/kitty-9292-0.scope
          Unit: user@1000.service
     User Unit: kitty-9292-0.scope
         Slice: user-1000.slice
     Owner UID: 1000 (johnathan)
       Boot ID: beb85b60a90d4537b67bd6cfb658c01c
    Machine ID: 67f7b96c12044f2584cf5ae9ed3e4200
      Hostname: fedora
       Storage: /var/lib/systemd/coredump/core.python3.1000.beb85b60a90d4537b67bd6cfb658c01c.9649.1783942586000000.zst (present)
  Size on Disk: 22.7M
       Package: python3.14/3.14.6-1.fc44
      build-id: 6bad9b4990db3650d45a1a8c2379b42aca033ef9
       Message: Process 9649 (python3) of user 1000 dumped core.
                
                Module libnss_resolve.so.2 from rpm systemd-259.7-1.fc44.x86_64
                Module libnss_mdns4_minimal.so.2 from rpm nss-mdns-0.15.1-28.fc44.x86_64
                Module libtinfo.so.6 from rpm ncurses-6.6-1.fc44.x86_64
                Module libpciaccess.so.0 from rpm libpciaccess-0.16-17.fc44.x86_64
                Module libedit.so.0 from rpm libedit-3.1-59.20260512cvs.fc44.x86_64
                Module libdrm_intel.so.1 from rpm libdrm-2.4.134-1.fc44.x86_64
                Module libdrm_amdgpu.so.1 from rpm libdrm-2.4.134-1.fc44.x86_64
                Module libxshmfence.so.1 from rpm libxshmfence-1.3.2-8.fc44.x86_64
                Module libxcb-sync.so.1 from rpm libxcb-1.17.0-7.fc44.x86_64
                Module libsensors.so.4 from rpm lm_sensors-3.6.0-24.fc44.x86_64
                Module libSPIRV-Tools.so from rpm spirv-tools-2026.1-1.fc44.x86_64
                Module libxcb-shm.so.0 from rpm libxcb-1.17.0-7.fc44.x86_64
                Module libxcb-xfixes.so.0 from rpm libxcb-1.17.0-7.fc44.x86_64
                Module libxcb-randr.so.0 from rpm libxcb-1.17.0-7.fc44.x86_64
                Module libgallium-26.1.4.so from rpm mesa-26.1.4-1.fc44.x86_64
                Module libEGL_mesa.so.0 from rpm mesa-26.1.4-1.fc44.x86_64
                Module libX11-xcb.so.1 from rpm libX11-1.8.13-1.fc44.x86_64
                Module libnvidia-egl-xlib.so.1 from rpm egl-x11-1.0.5-1.fc44.x86_64
                Module libxcb-dri3.so.0 from rpm libxcb-1.17.0-7.fc44.x86_64
                Module libxcb-present.so.0 from rpm libxcb-1.17.0-7.fc44.x86_64
                Module libnvidia-egl-xcb.so.1 from rpm egl-x11-1.0.5-1.fc44.x86_64
                Module libnvidia-egl-gbm.so.1 from rpm egl-gbm-1.1.3-2.fc44.x86_64
                Module libwayland-server.so.0 from rpm wayland-1.25.0-1.fc44.x86_64
                Module libnvidia-egl-wayland.so.1 from rpm egl-wayland-1.1.21-2.fc44.x86_64
                Module libgbm.so.1 from rpm mesa-26.1.4-1.fc44.x86_64
                Module libnvidia-egl-wayland2.so.1 from rpm egl-wayland2-1.0.1-1.fc44.x86_64
                Module libwayland-egl.so.1 from rpm wayland-1.25.0-1.fc44.x86_64
                Module libEGL.so.1 from rpm libglvnd-1.7.0-9.fc44.x86_64
                Module libnss_myhostname.so.2 from rpm systemd-259.7-1.fc44.x86_64
                Module libgstvolume.so from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libgstcoreelements.so from rpm gstreamer1-1.28.4-1.fc44.x86_64
                Module libgstautodetect.so from rpm gstreamer1-plugins-good-1.28.4-1.fc44.x86_64
                Module libgstplayback.so from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libelf.so.1 from rpm elfutils-0.195-1.fc44.x86_64
                Module libdw.so.1 from rpm elfutils-0.195-1.fc44.x86_64
                Module libunwind.so.8 from rpm libunwind-1.8.3-1.fc44.x86_64
                Module libgmodule-2.0.so.0 from rpm glib2-2.88.2-1.fc44.x86_64
                Module libdrm.so.2 from rpm libdrm-2.4.134-1.fc44.x86_64
                Module liborc-0.4.so.0 from rpm orc-0.4.41-3.fc44.x86_64
                Module libgsttag-1.0.so.0 from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libasound.so.2 from rpm alsa-lib-1.2.16.1-1.fc44.x86_64
                Module libgobject-2.0.so.0 from rpm glib2-2.88.2-1.fc44.x86_64
                Module libgstreamer-1.0.so.0 from rpm gstreamer1-1.28.4-1.fc44.x86_64
                Module libgstallocators-1.0.so.0 from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libgstpbutils-1.0.so.0 from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libgstbase-1.0.so.0 from rpm gstreamer1-1.28.4-1.fc44.x86_64
                Module libgstvideo-1.0.so.0 from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libgstaudio-1.0.so.0 from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libgstapp-1.0.so.0 from rpm gstreamer1-plugins-base-1.28.4-1.fc44.x86_64
                Module libbrotlicommon.so.1 from rpm brotli-1.2.0-3.fc44.x86_64
                Module libgraphite2.so.3 from rpm graphite2-1.3.14-20.fc44.x86_64
                Module libbrotlidec.so.1 from rpm brotli-1.2.0-3.fc44.x86_64
                Module libharfbuzz.so.0 from rpm harfbuzz-14.1.0-2.fc44.x86_64
                Module libpng16.so.16 from rpm libpng-1.6.58-1.fc44.x86_64
                Module libxml2.so.2 from rpm libxml2-2.12.10-6.fc44.x86_64
                Module libfreetype.so.6 from rpm freetype-2.14.3-1.fc44.x86_64
                Module libfontconfig.so.1 from rpm fontconfig-2.17.0-4.fc44.x86_64
                Module libwayland-client.so.0 from rpm wayland-1.25.0-1.fc44.x86_64
                Module libwayland-cursor.so.0 from rpm wayland-1.25.0-1.fc44.x86_64
                Module libxkbcommon.so.0 from rpm libxkbcommon-1.13.1-2.fc44.x86_64
                Module array.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _asyncio.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _interpreters.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libmpg123.so.0 from rpm mpg123-1.32.10-3.fc44.x86_64
                Module libogg.so.0 from rpm libogg-1.3.6-2.fc44.x86_64
                Module libopus.so.0 from rpm opus-1.6-2.fc44.x86_64
                Module libvorbisenc.so.2 from rpm libvorbis-1.3.7-14.fc44.x86_64
                Module libvorbis.so.0 from rpm libvorbis-1.3.7-14.fc44.x86_64
                Module libFLAC.so.14 from rpm flac-1.5.0-8.fc44.x86_64
                Module libgsm.so.1 from rpm gsm-1.0.24-2.fc44.x86_64
                Module libselinux.so.1 from rpm libselinux-3.10-1.fc44.x86_64
                Module libsystemd.so.0 from rpm systemd-259.7-1.fc44.x86_64
                Module libsndfile.so.1 from rpm libsndfile-1.2.2-11.fc44.x86_64
                Module libkeyutils.so.1 from rpm keyutils-1.6.3-7.fc44.x86_64
                Module libkrb5support.so.0 from rpm krb5-1.22.2-4.fc44.x86_64
                Module libcom_err.so.2 from rpm e2fsprogs-1.47.3-4.fc44.x86_64
                Module libk5crypto.so.3 from rpm krb5-1.22.2-4.fc44.x86_64
                Module libkrb5.so.3 from rpm krb5-1.22.2-4.fc44.x86_64
                Module libdbus-1.so.3 from rpm dbus-1.16.2-1.fc44.x86_64
                Module libpulsecommon-17.0.so from rpm pulseaudio-17.0-9.fc44.x86_64
                Module libgssapi_krb5.so.2 from rpm krb5-1.22.2-4.fc44.x86_64
                Module libpulse.so.0 from rpm pulseaudio-17.0-9.fc44.x86_64
                Module libpulse-mainloop-glib.so.0 from rpm pulseaudio-17.0-9.fc44.x86_64
                Module _multibytecodec.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module unicodedata.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _queue.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _heapq.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _hmac.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _brotli.cpython-314-x86_64-linux-gnu.so from rpm brotli-1.2.0-3.fc44.x86_64
                Module libexpat.so.1 from rpm expat-2.8.1-1.fc44.x86_64
                Module pyexpat.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _elementtree.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libffi.so.8 from rpm libffi-3.5.2-2.fc44.x86_64
                Module _cffi_backend.cpython-314-x86_64-linux-gnu.so from rpm python-cffi-2.0.0-3.fc44.x86_64
                Module _random.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _blake2.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _hashlib.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _bisect.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module binascii.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _socket.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libcrypto.so.3 from rpm openssl-3.5.7-1.fc44.x86_64
                Module libssl.so.3 from rpm openssl-3.5.7-1.fc44.x86_64
                Module _ssl.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _json.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libmpdec.so.4 from rpm mpdecimal-4.0.1-3.fc44.x86_64
                Module _decimal.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _struct.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libzstd.so.1 from rpm zstd-1.5.7-5.fc44.x86_64
                Module _zstd.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module liblzma.so.5 from rpm xz-5.8.2-2.fc44.x86_64
                Module _lzma.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libbz2.so.1 from rpm bzip2-1.0.8-23.fc44.x86_64
                Module _bz2.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module zlib.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libXau.so.6 from rpm libXau-1.0.12-4.fc44.x86_64
                Module libxcb.so.1 from rpm libxcb-1.17.0-7.fc44.x86_64
                Module libpcre2-8.so.0 from rpm pcre2-10.47-1.fc44.1.x86_64
                Module libGLdispatch.so.0 from rpm libglvnd-1.7.0-9.fc44.x86_64
                Module libXext.so.6 from rpm libXext-1.3.6-5.fc44.x86_64
                Module libX11.so.6 from rpm libX11-1.8.13-1.fc44.x86_64
                Module libGLX.so.0 from rpm libglvnd-1.7.0-9.fc44.x86_64
                Module libglib-2.0.so.0 from rpm glib2-2.88.2-1.fc44.x86_64
                Module libgthread-2.0.so.0 from rpm glib2-2.88.2-1.fc44.x86_64
                Module libz.so.1 from rpm zlib-ng-2.3.3-3.fc44.x86_64
                Module libGL.so.1 from rpm libglvnd-1.7.0-9.fc44.x86_64
                Module math.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module select.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module _posixsubprocess.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module fcntl.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module grp.cpython-314-x86_64-linux-gnu.so from rpm python3.14-3.14.6-1.fc44.x86_64
                Module libpython3.14.so.1.0 from rpm python3.14-3.14.6-1.fc44.x86_64
                Module python3.14 from rpm python3.14-3.14.6-1.fc44.x86_64
                Stack trace of thread 9649:
                #0  0x00007f517887bccc __pthread_kill_implementation (libc.so.6 + 0x74ccc)
                #1  0x00007f5178820e8e raise (libc.so.6 + 0x19e8e)
                #2  0x00007f51788087b3 abort (libc.so.6 + 0x17b3)
                #3  0x00007f5167c90b40 _ZNK14QMessageLogger5fatalEPKcz (libQt5Core.so.5 + 0x90b40)
                #4  0x00007f5167cb0e74 _ZN7QThreadD1Ev (libQt5Core.so.5 + 0xb0e74)
                #5  0x00007f5164b06fd9 _ZN10sipQThreadD0Ev (QtCore.abi3.so + 0x106fd9)
                #6  0x00007f5167ed01c5 _ZN7QObject5eventEP6QEvent (libQt5Core.so.5 + 0x2d01c5)
                #7  0x00007f5164bcee4b _ZN10sipQThread5eventEP6QEvent (QtCore.abi3.so + 0x1cee4b)
                #8  0x00007f516915e2bc _ZN19QApplicationPrivate13notify_helperEP7QObjectP6QEvent (libQt5Widgets.so.5 + 0x15e2bc)
                #9  0x00007f5169164d80 _ZN12QApplication6notifyEP7QObjectP6QEvent (libQt5Widgets.so.5 + 0x164d80)
                #10 0x00007f5169d7c6ce _ZN15sipQApplication6notifyEP7QObjectP6QEvent (QtWidgets.abi3.so + 0x37c6ce)
                #11 0x00007f5167ea0d98 _ZN16QCoreApplication15notifyInternal2EP7QObjectP6QEvent (libQt5Core.so.5 + 0x2a0d98)
                #12 0x00007f5167ea3e12 _ZN23QCoreApplicationPrivate16sendPostedEventsEP7QObjectiP11QThreadData (libQt5Core.so.5 + 0x2a3e12)
                #13 0x00007f5167efc3f3 _ZL23postEventSourceDispatchP8_GSourcePFiPvES1_ (libQt5Core.so.5 + 0x2fc3f3)
                #14 0x00007f51698e1f24 g_main_context_dispatch_unlocked.lto_priv.0 (libglib-2.0.so.0 + 0x43f24)
                #15 0x00007f51698e6038 g_main_context_iterate_unlocked.isra.0 (libglib-2.0.so.0 + 0x48038)
                #16 0x00007f51698e61e3 g_main_context_iteration (libglib-2.0.so.0 + 0x481e3)
                #17 0x00007f5167efba8c _ZN20QEventDispatcherGlib13processEventsE6QFlagsIN10QEventLoop17ProcessEventsFlagEE (libQt5Core.so.5 + 0x2fba8c)
                #18 0x00007f5167e9f76a _ZN10QEventLoop4execE6QFlagsINS_17ProcessEventsFlagEE (libQt5Core.so.5 + 0x29f76a)
                #19 0x00007f5167ea8773 _ZN16QCoreApplication4execEv (libQt5Core.so.5 + 0x2a8773)
                #20 0x00007f5169bf84e0 meth_QApplication_exec_ (QtWidgets.abi3.so + 0x1f84e0)
                #21 0x00007f5178bb52ce cfunction_call.lto_priv.0 (libpython3.14.so.1.0 + 0x1b52ce)
                #22 0x00007f5178b82c2b _PyObject_MakeTpCall.constprop.0 (libpython3.14.so.1.0 + 0x182c2b)
                #23 0x00007f5178a25089 _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x25089)
                #24 0x00007f5178b95d12 _PyEval_Vector.constprop.0 (libpython3.14.so.1.0 + 0x195d12)
                #25 0x00007f5178c9c58d PyEval_EvalCode (libpython3.14.so.1.0 + 0x29c58d)
                #26 0x00007f5178ce4855 run_mod.lto_priv.0 (libpython3.14.so.1.0 + 0x2e4855)
                #27 0x00007f5178ce57a6 pyrun_file.lto_priv.0 (libpython3.14.so.1.0 + 0x2e57a6)
                #28 0x00007f5178ce4fbc _PyRun_SimpleFileObject (libpython3.14.so.1.0 + 0x2e4fbc)
                #29 0x00007f5178ce47b5 _PyRun_AnyFileObject (libpython3.14.so.1.0 + 0x2e47b5)
                #30 0x00007f5178c89227 Py_RunMain (libpython3.14.so.1.0 + 0x289227)
                #31 0x00007f5178c8275c Py_BytesMain (libpython3.14.so.1.0 + 0x28275c)
                #32 0x00007f517880a681 __libc_start_call_main (libc.so.6 + 0x3681)
                #33 0x00007f517880a798 __libc_start_main@@GLIBC_2.34 (libc.so.6 + 0x3798)
                #34 0x0000561b8fc6d3d5 _start (python3.14 + 0x3d5)
                
                Stack trace of thread 9657:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876574 __syscall_cancel (libc.so.6 + 0x6f574)
                #3  0x00007f51788f0426 ppoll (libc.so.6 + 0xe9426)
                #4  0x00007f51698e6125 g_main_context_iterate_unlocked.isra.0 (libglib-2.0.so.0 + 0x48125)
                #5  0x00007f51698e61e3 g_main_context_iteration (libglib-2.0.so.0 + 0x481e3)
                #6  0x00007f5167efba8c _ZN20QEventDispatcherGlib13processEventsE6QFlagsIN10QEventLoop17ProcessEventsFlagEE (libQt5Core.so.5 + 0x2fba8c)
                #7  0x00007f5167e9f76a _ZN10QEventLoop4execE6QFlagsINS_17ProcessEventsFlagEE (libQt5Core.so.5 + 0x29f76a)
                #8  0x00007f5167cb1e84 _ZN7QThread4execEv (libQt5Core.so.5 + 0xb1e84)
                #9  0x00007f51604164e5 _ZN22QDBusConnectionManager3runEv (libQt5DBus.so.5 + 0x164e5)
                #10 0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #11 0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #12 0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 9654:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876574 __syscall_cancel (libc.so.6 + 0x6f574)
                #3  0x00007f51788fd8b5 epoll_wait (libc.so.6 + 0xf68b5)
                #4  0x00007f51786c8010 select_epoll_poll (select.cpython-314-x86_64-linux-gnu.so + 0x3010)
                #5  0x00007f5178a2df5d _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x2df5d)
                #6  0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #7  0x00007f5178c14f42 method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214f42)
                #8  0x00007f5178a28d1a _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x28d1a)
                #9  0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #10 0x00007f5178c14f42 method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214f42)
                #11 0x00007f5178d1f504 context_run.lto_priv.0 (libpython3.14.so.1.0 + 0x31f504)
                #12 0x00007f5178a24963 _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x24963)
                #13 0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #14 0x00007f5178c14f42 method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214f42)
                #15 0x00007f5178d1ef03 thread_run (libpython3.14.so.1.0 + 0x31ef03)
                #16 0x00007f5178d1ee8c pythread_wrapper (libpython3.14.so.1.0 + 0x31ee8c)
                #17 0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #18 0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 9655:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788790cc pthread_cond_wait@@GLIBC_2.3.2 (libc.so.6 + 0x720cc)
                #4  0x00007f5167cb9d23 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9d23)
                #5  0x00007f5169370ff0 _ZN17QFileInfoGatherer3runEv (libQt5Widgets.so.5 + 0x370ff0)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12055:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12054:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12059:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 13990:
                #0  0x00007f5163cadd0c __ecp_nistz256_mul_montx (libcrypto.so.3 + 0x2add0c)
                #1  0x00007f5163cafdaa ecp_nistz256_point_addx (libcrypto.so.3 + 0x2afdaa)
                #2  0x00007f5163ace761 ecp_nistz256_points_mul (libcrypto.so.3 + 0xce761)
                #3  0x00007f5163ab225c EC_POINT_mul (libcrypto.so.3 + 0xb225c)
                #4  0x00007f5163ab6698 ossl_ecdsa_simple_verify_sig (libcrypto.so.3 + 0xb6698)
                #5  0x00007f5163ab70d1 ossl_ecdsa_verify (libcrypto.so.3 + 0xb70d1)
                #6  0x00007f5163c6c3f2 ecdsa_verify_message_final.lto_priv.0 (libcrypto.so.3 + 0x26c3f2)
                #7  0x00007f5163c6c4e8 ecdsa_digest_verify_final.lto_priv.0 (libcrypto.so.3 + 0x26c4e8)
                #8  0x00007f5163b1c212 EVP_DigestVerifyFinal (libcrypto.so.3 + 0x11c212)
                #9  0x00007f51641a7f0b tls_process_cert_verify (libssl.so.3 + 0xa0f0b)
                #10 0x00007f5164199a40 state_machine (libssl.so.3 + 0x92a40)
                #11 0x00007f51671dd0b8 _ssl__SSLSocket_do_handshake (_ssl.cpython-314-x86_64-linux-gnu.so + 0x90b8)
                #12 0x00007f5178a24f27 _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x24f27)
                #13 0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #14 0x00007f5178c14e4a method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214e4a)
                #15 0x00007f5178a28d1a _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x28d1a)
                #16 0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #17 0x00007f5178c14f42 method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214f42)
                #18 0x00007f5165019713 call_method (sip.cpython-314-x86_64-linux-gnu.so + 0x19713)
                #19 0x00007f5164bceda3 _ZN10sipQThread3runEv (QtCore.abi3.so + 0x1ceda3)
                #20 0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #21 0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #22 0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 9658:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876574 __syscall_cancel (libc.so.6 + 0x6f574)
                #3  0x00007f51788efdfe __poll (libc.so.6 + 0xe8dfe)
                #4  0x00007f51786c79d0 select_poll_poll (select.cpython-314-x86_64-linux-gnu.so + 0x29d0)
                #5  0x00007f5178a2e0d1 _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x2e0d1)
                #6  0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #7  0x00007f5178c14f42 method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214f42)
                #8  0x00007f5178a28d1a _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x28d1a)
                #9  0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #10 0x00007f5178c14f42 method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214f42)
                #11 0x00007f5178d1f504 context_run.lto_priv.0 (libpython3.14.so.1.0 + 0x31f504)
                #12 0x00007f5178a2df5d _PyEval_EvalFrameDefault.cold (libpython3.14.so.1.0 + 0x2df5d)
                #13 0x00007f5178bc3044 _PyFunction_Vectorcall (libpython3.14.so.1.0 + 0x1c3044)
                #14 0x00007f5178c14f42 method_vectorcall.lto_priv.0 (libpython3.14.so.1.0 + 0x214f42)
                #15 0x00007f5178d1ef03 thread_run (libpython3.14.so.1.0 + 0x31ef03)
                #16 0x00007f5178d1ee8c pythread_wrapper (libpython3.14.so.1.0 + 0x31ee8c)
                #17 0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #18 0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12056:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12058:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12062:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12063:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12060:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12065:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 13887:
                #0  0x00007f51788fb37d syscall (libc.so.6 + 0xf437d)
                #1  0x00007f5167cb3595 _ZN11QBasicMutex12lockInternalEv (libQt5Core.so.5 + 0xb3595)
                #2  0x00007f5167cb35e6 _ZN6QMutex4lockEv (libQt5Core.so.5 + 0xb35e6)
                #3  0x00007f5167cb23bf _ZN12_GLOBAL__N_122terminate_on_exceptionIZN14QThreadPrivate6finishEPvEUlvE_EEvOT_ (libQt5Core.so.5 + 0xb23bf)
                #4  0x00007f5167cb3232 _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb3232)
                #5  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #6  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12064:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12057:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 12061:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876877 __GI___futex_abstimed_wait_cancelable64 (libc.so.6 + 0x6f877)
                #3  0x00007f51788792e2 pthread_cond_timedwait@@GLIBC_2.3.2 (libc.so.6 + 0x722e2)
                #4  0x00007f5167cb9cb4 _ZN14QWaitCondition4waitEP6QMutex14QDeadlineTimer (libQt5Core.so.5 + 0xb9cb4)
                #5  0x00007f5167cb6fd1 _ZN17QThreadPoolThread3runEv (libQt5Core.so.5 + 0xb6fd1)
                #6  0x00007f5167cb321d _ZN14QThreadPrivate5startEPv (libQt5Core.so.5 + 0xb321d)
                #7  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #8  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                
                Stack trace of thread 13991:
                #0  0x00007f5178882312 __syscall_cancel_arch (libc.so.6 + 0x7b312)
                #1  0x00007f517887652c __internal_syscall_cancel (libc.so.6 + 0x6f52c)
                #2  0x00007f5178876574 __syscall_cancel (libc.so.6 + 0x6f574)
                #3  0x00007f51788f0426 ppoll (libc.so.6 + 0xe9426)
                #4  0x00007f516524dfca pa_mainloop_poll (libpulse.so.0 + 0x12fca)
                #5  0x00007f5165258f91 pa_mainloop_iterate (libpulse.so.0 + 0x1df91)
                #6  0x00007f51637386f7 ma_device_data_loop__pulse (_ma_playback.abi3.so + 0x286f7)
                #7  0x00007f51637695f1 ma_worker_thread (_ma_playback.abi3.so + 0x595f1)
                #8  0x00007f5178879c19 start_thread (libc.so.6 + 0x72c19)
                #9  0x00007f51788fd5cc __clone3 (libc.so.6 + 0xf65cc)
                ELF object binary architecture: AMD x86-64

```