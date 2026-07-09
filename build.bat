@echo off
REM IPBanTool 打包脚本
REM 打包为单文件 exe，.env 和 templates 不包含在 exe 内

set VENV_PYTHON=D:\Claudecode\Project\AuthDash\.venv\Scripts\python.exe
set PROJECT_DIR=D:\Claudecode\Project\IPBanTool

cd /d %PROJECT_DIR%

%VENV_PYTHON% -m PyInstaller ^
  --onefile ^
  --name IPBanTool ^
  --add-data "templates;templates" ^
  --hidden-import uvicorn ^
  --hidden-import uvicorn.loggers ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.middleware ^
  --hidden-import uvicorn.middleware.proxy_headers ^
  --hidden-import alibabacloud_cloudfw20171207 ^
  --hidden-import alibabacloud_tea_openapi ^
  --hidden-import tencentcloud.vpc.v20170312 ^
  --hidden-import tencentcloud.cvm.v20170312 ^
  --hidden-import tencentcloud.common ^
  --hidden-import tencentcloud.common.exception.tencent_cloud_sdk_exception ^
  --hidden-import dotenv ^
  --hidden-import ipaddress ^
  --hidden-import multiprocessing ^
  main.py

echo.
echo 打包完成！exe 位于 dist\IPBanTool.exe
echo 运行前请在 exe 同级目录创建 .env 文件
