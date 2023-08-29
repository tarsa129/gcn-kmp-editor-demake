from struct import pack, unpack
from io import BytesIO
import os
import shutil


def clear_temp_folder():
    for file in os.listdir("lib/szsdump/"):
        try:
            filepath = os.path.join(os.getcwd(), "lib/szsdump/", file)
            if os.path.isfile(filepath):
                os.remove(filepath)
            else:
                shutil.rmtree(filepath)
        except Exception as err:
            print("Failed to remove", os.path.join("lib/szsdump/", file), str(err))
            pass

def split_path(path): # Splits path at first backslash encountered
    for i, char in enumerate(path):
        if char == "/" or char == "\\":
            if len(path) == i+1:
                return path[:i], None
            else:
                return path[:i], path[i+1:]

    return path, None


class Directory(object):
    def __init__(self, dirname):
        self.files = {}
        self.subdirs = {}
        self.name = dirname
        self.parent = None

    @classmethod
    def from_dir(cls, path, follow_symlinks=False):
        dirname = os.path.basename(path)
        dir = cls(dirname)

        #with os.scandir(path) as entries: <- not supported in versions earlier than 3.6 apparently
        for entry in os.scandir(path):
            if entry.is_dir(follow_symlinks=follow_symlinks):
                newdir = Directory.from_dir(entry.path, follow_symlinks=follow_symlinks)
                dir.subdirs[entry.name] = newdir

            elif entry.is_file(follow_symlinks=follow_symlinks):
                with open(entry.path, "rb") as f:
                    file = File.from_file(entry.name, f)
                dir.files[entry.name] = file

        return dir

    def get_file(self, name):
        if name in self.files:
            return self.files[name]
        return None

    def walk(self, _path=None):
        if _path is None:
            dirpath = self.name
        else:
            dirpath = _path+"/"+self.name


        yield (dirpath, self.subdirs.keys(), self.files.keys())

        for dirname, dir in self.subdirs.items():
            yield from dir.walk(dirpath)

    def __getitem__(self, path):
        name, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if name in self.subdirs:
                return self.subdirs[name]
            elif name in self.files:
                return self.files[name]
            else:
                raise FileNotFoundError(path)
        elif name in self.files:
            raise RuntimeError("File", name, "is a directory in path", path, "which should not happen!")
        else:
            return self.subdirs[name][rest]

    def __setitem__(self, path, entry):
        name, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if isinstance(name, File):
                if name in self.subdirs:
                    raise FileExistsError("Cannot add file, '{}' already exists as a directory".format(path))

                self.files[name] = entry
            elif isinstance(name, Directory):
                if name in self.files:
                    raise FileExistsError("Cannot add directory, '{}' already exists as a file".format(path))

                self.subdirs[name] = entry
            else:
                raise TypeError("Entry should be of type File or Directory but is type {}".format(type(entry)))

        elif name in self.files:
            raise RuntimeError("File", name, "is a directory in path", path, "which should not happen!")
        else:
            return self.subdirs[name][rest]

    def listdir(self, path):
        if path == ".":
            dir = self
        else:
            dir = self[path]

        entries = []
        entries.extend(dir.files.keys())
        entries.extend(dir.subdirs.keys())
        return entries

    def extract_to(self, path):
        current_dirpath = os.path.join(path, self.name)
        os.makedirs(current_dirpath, exist_ok=True)

        for filename, file in self.files.items():
            filepath = os.path.join(current_dirpath, filename)
            with open(filepath, "wb") as f:
                file.dump(f)

        for dirname, dir in self.subdirs.items():
            dir.extract_to(current_dirpath)

class File(BytesIO):
    def __init__(self, filename, fileid=None, hashcode=None, flags=None):
        super().__init__()

        self.name = filename
        self._fileid = fileid
        self._hashcode = hashcode
        self._flags = flags

    @classmethod
    def from_file(cls, filename, f):
        file = cls(filename)

        file.write(f.read())
        file.seek(0)

        return file

    def dump(self, f):
        f.write(self.getvalue())