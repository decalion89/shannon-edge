"""Tests for the Python binding (stdlib unittest; run from the repo root):

    cargo build --release
    python3 -m unittest discover -s python -v
"""

import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shannon_edge as se  # noqa: E402

TEXT = b"the information entropy of a source is the limit below which no lossless code can go. " * 40


def events(n: int, seed: int = 1) -> list:
    r = random.Random(seed)
    return [
        json.dumps({"device": f"sensor-{r.randrange(4)}", "seq": i, "temp": round(15 + r.random() * 10, 1),
                    "status": "warn" if r.random() < 0.2 else "ok"}).encode()
        for i in range(n)
    ]


class OneShot(unittest.TestCase):
    def test_roundtrip_and_ratio(self):
        packed = se.compress(TEXT)
        self.assertLess(len(packed), len(TEXT) // 10)
        self.assertEqual(se.decompress(packed), TEXT)

    def test_empty_and_random(self):
        self.assertEqual(se.decompress(se.compress(b"")), b"")
        noise = random.Random(7).randbytes(5000)
        packed = se.compress(noise)
        self.assertLessEqual(len(packed), len(noise) + 20)
        self.assertEqual(se.decompress(packed), noise)

    def test_corruption_raises(self):
        packed = bytearray(se.compress(TEXT))
        packed[len(packed) // 2] ^= 0x40
        with self.assertRaises(se.SedgeError):
            se.decompress(bytes(packed))
        with self.assertRaises(se.SedgeError) as cm:
            se.decompress(b"not a stream at all")
        self.assertEqual(cm.exception.code, -3)

    def test_bad_memory_level_is_an_error_not_a_crash(self):
        with self.assertRaises(se.SedgeError):
            se.compress(TEXT, mem_bits=99)

    def test_dictionary(self):
        dictionary = b"".join(events(300, seed=2))
        msg = events(1, seed=3)[0]
        packed = se.compress(msg, dictionary=dictionary)
        self.assertEqual(se.decompress(packed, dictionary=dictionary), msg)
        with self.assertRaises(se.SedgeError) as cm:
            se.decompress(packed)
        self.assertEqual(cm.exception.code, -10)


class Models(unittest.TestCase):
    def test_model_messages_save_load(self):
        dictionary = b"".join(events(300, seed=2))
        with se.PrimedModel(dictionary, mem_bits=18) as model:
            msgs = events(20, seed=5)
            frames = [model.compress(m) for m in msgs]
            self.assertEqual([model.decompress(f) for f in frames], msgs)
            # Streams also decode with the raw dictionary.
            self.assertEqual(se.decompress(frames[0], dictionary=dictionary), msgs[0])
            saved = model.save()
        with se.PrimedModel.load(saved) as again:
            self.assertEqual(again.compress(msgs[3]), frames[3])
        with self.assertRaises(se.SedgeError):
            se.PrimedModel.load(saved[:-1])


class Sessions(unittest.TestCase):
    def test_session_learns_and_stays_in_sync(self):
        tx, rx = se.Session(mem_bits=18), se.Session(mem_bits=18)
        records = events(300)
        sizes = []
        for r in records:
            frame = tx.compress(r)
            sizes.append(len(frame))
            self.assertEqual(rx.decompress(frame), r)
        self.assertLess(sum(sizes[-20:]), sum(sizes[:20]))

    def test_out_of_order_and_corrupt(self):
        tx, rx = se.Session(mem_bits=16), se.Session(mem_bits=16)
        a, b = tx.compress(b"first record"), tx.compress(b"second record")
        with self.assertRaises(se.SedgeError) as cm:
            rx.decompress(b)
        self.assertEqual(cm.exception.code, -13)
        bad = bytearray(a)
        bad[-1] ^= 0xFF
        bad[7] ^= 0x01  # inside the CRC field: always detected
        with self.assertRaises(se.SedgeError):
            rx.decompress(bytes(bad))
        self.assertEqual(rx.decompress(a), b"first record")
        self.assertEqual(rx.decompress(b), b"second record")

    def test_session_from_model(self):
        dictionary = b"".join(events(300, seed=2))
        model = se.PrimedModel(dictionary, mem_bits=18)
        tx, rx = se.Session(model), se.Session(model)
        for r in events(30, seed=9):
            self.assertEqual(rx.decompress(tx.compress(r)), r)


if __name__ == "__main__":
    print("shannon-edge", se.version())
    unittest.main()
