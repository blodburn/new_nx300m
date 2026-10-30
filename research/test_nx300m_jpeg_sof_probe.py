import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from nx300m_jpeg_sof_probe import probe_bytes,JPEGHeaderError
def mkjpeg(y_hv,sof=0xc0):
    sofdata=bytes([8,0,4,0,6,3,1,y_hv,0,2,0x11,1,3,0x11,1])
    return b'\xff\xd8'+b'\xff\xe0\x00\x04AB'+bytes([0xff,sof])+len(sofdata+ b'AB').to_bytes(2,'big')+sofdata+b'\xff\xd9'
class ProbeTest(unittest.TestCase):
 def test_420(self):
    a=probe_bytes(mkjpeg(0x22))
    self.assertEqual(a["chroma_subsampling"],"4:2:0")
    self.assertEqual((a["width"],a["height"]),(6,4))
    self.assertEqual(a["components"][0]["v"],2)
 def test_422(self):
    self.assertEqual(probe_bytes(mkjpeg(0x21))["chroma_subsampling"],"4:2:2")
 def test_444(self):
    self.assertEqual(probe_bytes(mkjpeg(0x11))["chroma_subsampling"],"4:4:4")
 def test_progressive(self):
    self.assertEqual(probe_bytes(mkjpeg(0x22,0xc2))["jpeg_encoding"],"Progressive DCT")
 def test_invalid(self):
    for sample in (b"",b'abc',b'\xff\xd8\xff\xd9',b'\xff\xd8\xff\xc0\x00\x10\x08'):
       with self.assertRaises(JPEGHeaderError):probe_bytes(sample)
if __name__=="__main__":
 unittest.main(verbosity=2)
