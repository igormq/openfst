import glob
import os
import pathlib
import platform
import re
import shutil
import sys
from distutils.dir_util import copy_tree
from shutil import rmtree

from setuptools import Command, Extension, setup
from setuptools.command.build_ext import build_ext as build_ext_orig

IS_WINDOWS = (platform.system() == 'Windows')
IS_DARWIN = (platform.system() == 'Darwin')
IS_LINUX = (platform.system() == 'Linux')


def read(*names, **kwargs):
    with open(os.path.join(os.path.dirname(__file__), *names)) as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def make_relative_rpath(path):
    if IS_DARWIN:
        return '-Wl,-rpath,@loader_path/' + path
    elif IS_WINDOWS:
        return ''
    else:
        return '-Wl,-rpath,$ORIGIN/' + path


readme = read('README.rst')
VERSION = find_version('src/extensions/python/openfst', '__init__.py')


class UploadCommand(Command):
    """Support setup.py upload."""
    description = 'Build and publish the package.'
    user_options = []

    @staticmethod
    def status(s):
        """Prints things in bold."""
        print('\033[1m{0}\033[0m'.format(s))

    def initialize_options(self):
        """Initialization options."""
        pass

    def finalize_options(self):
        """Finalize options."""
        pass

    def run(self):
        """Remove previous builds."""
        try:
            self.status('Removing previous builds...')
            rmtree(os.path.join(pathlib.Path().absolute(), 'dist'))
        except OSError:
            pass

        self.status('Building Source and Wheel distribution...')
        os.system('{0} setup.py sdist'.format(sys.executable))

        self.status('Uploading the package to PyPI via Twine...')
        os.system('twine upload dist/*')

        sys.exit()


class build_ext(build_ext_orig):
    def run(self):
        for ext in self.extensions:
            self.build_make(ext)

        super().run()

    def build_make(self, ext):
        cwd = pathlib.Path().absolute()

        # these dirs will be created in build_py, so if you don't have
        # any python sources to bundle, the dirs will be missing
        build_temp = pathlib.Path(self.build_temp).absolute()
        build_temp.mkdir(parents=True, exist_ok=True)

        local_temp = (pathlib.Path(self.build_temp) / 'local').absolute()
        local_temp.mkdir(parents=True, exist_ok=True)

        configure_args = ['-q', '--enable-far', '--prefix=' + str(local_temp)]

        os.chdir(str(build_temp))
        self.spawn([str(cwd / 'configure')] + configure_args)

        config_h = pathlib.PurePath('config.h')
        inc_fst_config_h = pathlib.PurePath('src', 'include', 'fst', 'config.h')

        # Create symbolic link to config.h
        if (cwd / config_h).exists():
            os.unlink(str(cwd / config_h))
        os.symlink(str(build_temp / config_h), str(cwd / config_h))

        if (cwd / inc_fst_config_h).exists():
            os.unlink(str(cwd / inc_fst_config_h))
        os.symlink(str(build_temp / inc_fst_config_h), str(cwd / inc_fst_config_h))

        if not self.dry_run:
            self.spawn(['make', '-s', '-j', '4'])
            self.spawn(['make', '-s', '-j', '4', 'install'])

        self.include_dirs.append(str(local_temp / 'include'))
        self.library_dirs.append(str(local_temp / 'lib'))

        os.chdir(str(cwd))

        local_temp = (pathlib.Path(self.build_temp) / 'local').absolute() / 'lib'
        build_lib = pathlib.Path(self.build_lib).absolute() / 'openfst' / 'lib'
        copy_tree(str(local_temp), str(build_lib))


install_requires = []

extra_compile_args, libraries = [], []

extra_compile_args += ['-O3', '-DNDEBUG', '-std=c++11']
extra_compile_args += ['-fno-exceptions', '-funsigned-char', '-fexceptions']

if IS_LINUX:
    libraries += ['stdc++', 'rt']
elif IS_DARWIN:
    libraries += ['stdc++']

# OpenFST required libraries
libraries += ['fstfar', 'fstfarscript', 'fstscript', 'fst']

if '--use-cython' in sys.argv:
    USE_CYTHON = True
    sys.argv.remove('--use-cython')
    install_requires += ["cython"]
else:
    USE_CYTHON = False

ext = '.pyx' if USE_CYTHON else '.cpp'

files = ['src/extensions/python/pywrapfst{}'.format(ext)]

ext_modules = [
    Extension(
        'openfst.pywrapfst',
        sources=files,
        include_dirs=['.'],
        libraries=libraries,
        language='c++',
        extra_compile_args=extra_compile_args,
        extra_link_args=[make_relative_rpath('lib')])
]

if USE_CYTHON:
    from Cython.Build import cythonize
    ext_modules = cythonize(ext_modules)

setup(
    name='pyopenfst',
    version=VERSION,
    description='OpenFST unofficial support for Python 3+',
    author='Igor Macedo Quintanilha',
    author_email='igormq@poli.ufrj.br',
    url='http://github.com/igormq/pyopenfst',
    ext_modules=ext_modules,
    install_requires=install_requires,
    long_description=readme,
    package_dir={'': 'src/extensions/python'},
    packages=['openfst'],
    package_data={'': ['lib/*.so*', 'lib/*.dylib*', 'lib/*.dll', 'lib/*.lib']},
    cmdclass={
        'build_ext': build_ext,
        'upload': UploadCommand
    },
    zip_safe=False,
    classifiers=(
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ),
    keywords='fst finite state transducer wfst')
