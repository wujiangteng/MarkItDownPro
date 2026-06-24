import torch
from transformers import StoppingCriteria


class DetectRepeatingNgramCriteria(StoppingCriteria):
    """
    Stops generation efficiently if any n-gram repeats.

    This criteria maintains a set of encountered n-grams.
    At each step, it checks if the *latest* n-gram is already in the set.
    If yes, it stops generation. If no, it adds the n-gram to the set.
    """

    def __init__(self, n: int):
        """
        Args:
            n (int): The size of the n-gram to check for repetition.
        """
        if n <= 0:
            raise ValueError("n-gram size 'n' must be positive.")
        self.n = n
        # Stores tuples of token IDs representing seen n-grams
        self.seen_ngrams = set()

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor, **kwargs) -> bool:
        """
        Args:
            input_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`):
                Indices of input sequence tokens in the vocabulary.
            scores (`torch.FloatTensor` of shape `(batch_size, config.vocab_size)`):
                Prediction scores.

        Return:
            `bool`: `True` if generation should stop, `False` otherwise.
        """
        batch_size, seq_length = input_ids.shape

        # Need at least n tokens to form the first n-gram
        if seq_length < self.n:
            return False

        # --- Efficient Check ---
        # Consider only the first sequence in the batch for simplicity
        if batch_size > 1:
            # If handling batch_size > 1, you'd need a list of sets, one per batch item.
            # Or decide on a stopping policy (e.g., stop if *any* sequence repeats).
            # For now, we'll focus on the first sequence.
            pass  # No warning needed every step, maybe once in __init__ if needed.

        sequence = input_ids[0]  # Get the first sequence

        # Get the latest n-gram (the one ending at the last token)
        last_ngram_tensor = sequence[-self.n :]
        # Convert to a hashable tuple for set storage and lookup
        last_ngram_tuple = tuple(last_ngram_tensor.tolist())

        # Check if this n-gram has been seen before *at any prior step*
        if last_ngram_tuple in self.seen_ngrams:
            return True  # Stop generation
        else:
            # It's a new n-gram, add it to the set and continue
            self.seen_ngrams.add(last_ngram_tuple)
            return False  # Continue generation
