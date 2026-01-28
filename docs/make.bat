@ECHO OFF

pushd %~dp0

REM Command file for Sphinx documentation
REM Uses uv run to execute sphinx-build in the virtual environment

set SOURCEDIR=.
set BUILDDIR=_build

if "%1" == "" goto help

uv run sphinx-build -M %1 %SOURCEDIR% %BUILDDIR% %SPHINXOPTS% %O%
goto end

:help
uv run sphinx-build -M help %SOURCEDIR% %BUILDDIR% %SPHINXOPTS% %O%

:end
popd
