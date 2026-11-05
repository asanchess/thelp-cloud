import io,json,tarfile,tempfile,unittest
from pathlib import Path
from offline_llm import OfflineError,unpack,LocalModel

class OfflineTests(unittest.TestCase):
    def test_internal_library_link_is_copied_without_creating_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'engine.tar'
            with tarfile.open(archive,'w') as tar:
                member=tarfile.TarInfo('bin/lib.so.1');member.size=3;tar.addfile(member,io.BytesIO(b'abc'))
                link=tarfile.TarInfo('bin/lib.so');link.type=tarfile.SYMTYPE;link.linkname='lib.so.1';tar.addfile(link)
            unpack(archive,root/'out')
            self.assertEqual((root/'out/bin/lib.so').read_bytes(),b'abc')
            self.assertFalse((root/'out/bin/lib.so').is_symlink())
    def test_traversal_and_external_links_are_rejected(self):
        for name,link in [('../escape',''),('lib.so','../../outside')]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);archive=root/'engine.tar'
                with tarfile.open(archive,'w') as tar:
                    member=tarfile.TarInfo(name)
                    if link:member.type=tarfile.SYMTYPE;member.linkname=link
                    tar.addfile(member)
                with self.assertRaises(OfflineError):unpack(archive,root/'out')
                self.assertFalse((root/'escape').exists())
    def test_context_is_checked_before_generation(self):
        model=LocalModel(Path('.'),context=100)
        model.tokens=lambda text:100
        model.request=lambda *args,**kwargs:self.fail('No generation request allowed')
        with self.assertRaises(OfflineError):model.infer('test',{},max_tokens=30)

if __name__=='__main__':unittest.main()
