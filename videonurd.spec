# -*- mode: python -*-
a = Analysis(['videonurd.py'],
             pathex=['/home/baxter/VideoNurd'],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None)
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='videonurd',
          debug=False,
          strip=None,
          upx=True,
          console=True )
