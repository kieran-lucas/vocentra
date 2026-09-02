use crate::models::Rating;
use rand::{Rng, SeedableRng, rngs::SmallRng};

const MIN_GAP: usize = 2;
const MAX_REPEAT_STREAK: usize = 2;
const MAX_APPEARANCES: usize = 7;
#[derive(Clone, Debug)]
pub struct ItemState {
    pub seen: usize,
    pub appearances: usize,
    pub last_seen: Option<usize>,
    pub debt: i32,
    pub mastery: i64,
}
pub struct Scheduler {
    pub items: Vec<ItemState>,
    index: usize,
    repeat_streak: usize,
    rng: SmallRng,
}
impl Scheduler {
    pub fn new(scores: Vec<i64>, seed: u64) -> Self {
        Self {
            items: scores
                .into_iter()
                .map(|mastery| ItemState {
                    seen: 0,
                    appearances: 0,
                    last_seen: None,
                    debt: 0,
                    mastery,
                })
                .collect(),
            index: 0,
            repeat_streak: 0,
            rng: SmallRng::seed_from_u64(seed),
        }
    }
    pub fn covered(&self) -> usize {
        self.items.iter().filter(|i| i.seen > 0).count()
    }
    pub fn total_shown(&self) -> usize {
        self.index
    }
    pub fn complete(&self) -> bool {
        !self.items.is_empty() && self.covered() == self.items.len()
    }
    pub fn next(&mut self) -> Option<usize> {
        if self.items.is_empty() || self.complete() {
            return None;
        }
        let unseen: Vec<usize> = self
            .items
            .iter()
            .enumerate()
            .filter(|(_, s)| s.seen == 0)
            .map(|(i, _)| i)
            .collect();
        let mut repeat: Vec<(usize, i32)> = self
            .items
            .iter()
            .enumerate()
            .filter(|(_, s)| {
                s.seen > 0
                    && s.appearances < MAX_APPEARANCES
                    && s.debt > 0
                    && s.last_seen
                        .is_none_or(|last| self.index.saturating_sub(last) > MIN_GAP)
            })
            .map(|(i, s)| {
                (
                    i,
                    s.debt
                        + (self.items.iter().map(|x| x.mastery).max().unwrap_or(0) - s.mastery)
                            .clamp(0, 8) as i32,
                )
            })
            .collect();
        let choose_repeat = !repeat.is_empty()
            && self.repeat_streak < MAX_REPEAT_STREAK
            && self.rng.random_range(0..100) < 70;
        let chosen = if choose_repeat {
            repeat.sort_by_key(|(_, p)| -*p);
            let top = repeat[0].1;
            let peers: Vec<_> = repeat.into_iter().filter(|(_, p)| *p >= top - 1).collect();
            peers[self.rng.random_range(0..peers.len())].0
        } else {
            self.repeat_streak = 0;
            unseen[self.rng.random_range(0..unseen.len())]
        };
        let state = &mut self.items[chosen];
        if state.seen > 0 {
            state.debt = (state.debt - 2).max(0);
            self.repeat_streak += 1
        }
        state.seen += 1;
        state.appearances += 1;
        state.last_seen = Some(self.index);
        self.index += 1;
        Some(chosen)
    }
    pub fn rate(&mut self, item: usize, rating: Rating) {
        let delta = match rating {
            Rating::Again => 6,
            Rating::Hard => 3,
            Rating::Good => 1,
            Rating::Easy => -3,
        };
        self.items[item].debt = (self.items[item].debt + delta).clamp(0, 12);
        self.items[item].mastery += rating.points();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn run(rating_for: impl Fn(usize) -> Rating) -> (Vec<usize>, usize) {
        let mut s = Scheduler::new(vec![0; 12], 42);
        let mut counts = vec![0; 12];
        let mut steps = 0;
        while let Some(i) = s.next() {
            counts[i] += 1;
            s.rate(i, rating_for(i));
            steps += 1;
            assert!(steps < 84)
        }
        (counts, steps)
    }
    #[test]
    fn coverage_and_easy_efficiency() {
        let (c, n) = run(|_| Rating::Easy);
        assert!(c.iter().all(|x| *x == 1));
        assert_eq!(n, 12)
    }
    #[test]
    fn again_gets_repeat_pressure_without_starvation() {
        let (c, _) = run(|i| if i == 0 { Rating::Again } else { Rating::Easy });
        assert!(c[0] > 1);
        assert!(c.iter().all(|x| *x >= 1));
    }
    #[test]
    fn cooldown_prevents_immediate_repeat() {
        let mut s = Scheduler::new(vec![0; 10], 7);
        let mut last = None;
        while let Some(i) = s.next() {
            if let Some(previous) = last {
                assert_ne!(i, previous)
            }
            s.rate(i, Rating::Again);
            last = Some(i)
        }
    }
    #[test]
    fn relative_pressure_is_ordered() {
        fn count(r: Rating) -> usize {
            let (c, _) = run(|i| if i == 0 { r } else { Rating::Easy });
            c[0]
        }
        let values = [
            count(Rating::Again),
            count(Rating::Hard),
            count(Rating::Good),
            count(Rating::Easy),
        ];
        assert!(
            values[0] >= values[1] && values[1] >= values[2] && values[2] >= values[3],
            "{values:?}"
        );
    }
    #[test]
    fn pathological_input_terminates() {
        let (c, n) = run(|_| Rating::Again);
        assert!(c.iter().all(|x| *x >= 1));
        assert!(n <= 12 * MAX_APPEARANCES)
    }
}
