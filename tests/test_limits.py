import unittest

from pipeline import limits
from tests import fixtures


class LimiterCase(unittest.TestCase):
    def setUp(self):
        self.clock = fixtures.FakeClock()
        self.start = self.clock()

    def limiter(self, **options):
        return limits.Limiter(clock=self.clock, sleep=self.clock.advance, **options)

    def elapsed(self):
        return self.clock() - self.start


class Requests(LimiterCase):
    def test_150_acquires_at_75_a_second_take_about_two_seconds(self):
        lim = self.limiter(requests_per_second=75)
        for _ in range(150):
            lim.acquire(2400)
        self.assertAlmostEqual(self.elapsed(), 149 / 75, places=6)

    def test_the_first_acquire_does_not_wait(self):
        self.limiter().acquire(2400)
        self.assertEqual(self.elapsed(), 0)

    def test_idle_time_is_not_saved_up_into_a_burst(self):
        lim = self.limiter(requests_per_second=10)
        lim.acquire(100)
        self.clock.advance(60)
        before = self.clock()
        for _ in range(11):
            lim.acquire(100)
        self.assertAlmostEqual(self.clock() - before, 1.0, places=6)


class Tokens(LimiterCase):
    def test_a_large_body_is_held_by_the_token_limit(self):
        lim = self.limiter(requests_per_second=75, tokens_per_second=100_000)
        for _ in range(3):
            lim.acquire(240_000)  # 100,000 estimated tokens each
        self.assertAlmostEqual(self.elapsed(), 2.0, places=6)

    def test_small_bodies_are_held_by_the_request_limit_not_the_token_limit(self):
        lim = self.limiter(requests_per_second=75, tokens_per_second=100_000)
        for _ in range(76):
            lim.acquire(2400)  # 1,000 tokens each: 75,000 a second, under the token limit
        self.assertAlmostEqual(self.elapsed(), 1.0, places=6)

    def test_tokens_are_estimated_as_bytes_over_2_4(self):
        self.assertEqual(limits.estimate_tokens(2400), 1000)
        self.assertEqual(limits.estimate_tokens(1), 1)


class After429(LimiterCase):
    def test_a_429_halves_the_rate(self):
        lim = self.limiter(requests_per_second=75)
        lim.on_429()
        self.assertEqual(lim.rate(), 37.5)

    def test_two_429s_inside_ten_seconds_halve_the_rate_once(self):
        lim = self.limiter(requests_per_second=75, recover_per_second=0)
        lim.on_429()
        self.clock.advance(9)
        lim.on_429()
        self.assertEqual(lim.rate(), 37.5)
        self.clock.advance(1.5)
        lim.on_429()
        self.assertEqual(lim.rate(), 18.75)

    def test_the_rate_climbs_back_and_never_passes_its_ceiling(self):
        lim = self.limiter(requests_per_second=75, recover_per_second=1)
        lim.on_429()
        self.clock.advance(10)
        self.assertEqual(lim.rate(), 47.5)
        self.clock.advance(1000)
        self.assertEqual(lim.rate(), 75)

    def test_the_halved_rate_is_the_one_acquires_are_paced_at(self):
        lim = self.limiter(requests_per_second=10, recover_per_second=0)
        lim.on_429()
        before = self.clock()
        for _ in range(6):
            lim.acquire(100)
        self.assertAlmostEqual(self.clock() - before, 1.0, places=6)

    def test_the_rate_never_falls_below_one_a_second(self):
        lim = self.limiter(requests_per_second=2, recover_per_second=0)
        for _ in range(5):
            lim.on_429()
            self.clock.advance(11)
        self.assertEqual(lim.rate(), 1)


if __name__ == "__main__":
    unittest.main()
