import unittest
from src.jeap_pipeline import hello_jeap


class TestHelloWorld(unittest.TestCase):
    def test_say_hello(self):
        self.assertIsNone(hello_jeap.say_hello())


if __name__ == '__main__':
    unittest.main()
