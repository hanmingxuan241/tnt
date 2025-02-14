# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

from collections.abc import Sized
from typing import Iterable, Optional

from torchtnt.runner.callback import Callback
from torchtnt.runner.state import State
from torchtnt.runner.unit import (
    EvalUnit,
    PredictUnit,
    TEvalData,
    TPredictData,
    TrainUnit,
    TTrainData,
)
from torchtnt.utils.distributed import get_global_rank
from tqdm.auto import tqdm


class TQDMProgressBar(Callback):
    """
    A callback for progress bar visualization in training, evaluation, and prediction.
    It is initialized only on rank 0 in distributed environments.

    Args:
        refresh_rate: Determines at which rate (in number of steps) the progress bars get updated.
    """

    def __init__(self, refresh_rate: int = 1) -> None:
        self._refresh_rate = refresh_rate

        self._train_progress_bar: Optional[tqdm] = None
        self._eval_progress_bar: Optional[tqdm] = None
        self._predict_progress_bar: Optional[tqdm] = None

    def on_train_epoch_start(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        if state.train_state:
            self._train_progress_bar = _create_progress_bar(
                state.train_state.dataloader,
                desc="Train Epoch",
                num_epochs_completed=state.train_state.progress.num_epochs_completed,
                num_steps_completed=state.train_state.progress.num_steps_completed,
                max_steps=state.train_state.max_steps,
                max_steps_per_epoch=state.train_state.max_steps_per_epoch,
            )

    def on_train_step_end(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        if self._train_progress_bar and state.train_state:
            _update_progress_bar(
                self._train_progress_bar,
                state.train_state.progress.num_steps_completed,
                self._refresh_rate,
            )

    def on_train_epoch_end(self, state: State, unit: TrainUnit[TTrainData]) -> None:
        if self._train_progress_bar and state.train_state:
            _close_progress_bar(
                self._train_progress_bar,
                state.train_state.progress.num_steps_completed,
                self._refresh_rate,
            )

    def on_eval_epoch_start(self, state: State, unit: EvalUnit[TEvalData]) -> None:
        if state.eval_state:
            self._eval_progress_bar = _create_progress_bar(
                state.eval_state.dataloader,
                desc="Eval Epoch",
                num_epochs_completed=state.eval_state.progress.num_epochs_completed,
                num_steps_completed=state.eval_state.progress.num_steps_completed,
                max_steps=state.eval_state.max_steps,
                max_steps_per_epoch=state.eval_state.max_steps_per_epoch,
            )

    def on_eval_step_end(self, state: State, unit: EvalUnit[TEvalData]) -> None:
        if self._eval_progress_bar and state.eval_state:
            _update_progress_bar(
                self._eval_progress_bar,
                state.eval_state.progress.num_steps_completed,
                self._refresh_rate,
            )

    def on_eval_epoch_end(self, state: State, unit: EvalUnit[TEvalData]) -> None:
        if self._eval_progress_bar and state.eval_state:
            _close_progress_bar(
                self._eval_progress_bar,
                state.eval_state.progress.num_steps_completed,
                self._refresh_rate,
            )

    def on_predict_epoch_start(
        self, state: State, unit: PredictUnit[TPredictData]
    ) -> None:
        if state.predict_state:
            self._predict_progress_bar = _create_progress_bar(
                state.predict_state.dataloader,
                desc="Predict Epoch",
                num_epochs_completed=state.predict_state.progress.num_epochs_completed,
                num_steps_completed=state.predict_state.progress.num_steps_completed,
                max_steps=state.predict_state.max_steps,
                max_steps_per_epoch=state.predict_state.max_steps_per_epoch,
            )

    def on_predict_step_end(
        self, state: State, unit: PredictUnit[TPredictData]
    ) -> None:
        if self._predict_progress_bar and state.predict_state:
            _update_progress_bar(
                self._predict_progress_bar,
                state.predict_state.progress.num_steps_completed,
                self._refresh_rate,
            )

    def on_predict_epoch_end(
        self, state: State, unit: PredictUnit[TPredictData]
    ) -> None:
        if self._predict_progress_bar and state.predict_state:
            _close_progress_bar(
                self._predict_progress_bar,
                state.predict_state.progress.num_steps_completed,
                self._refresh_rate,
            )


def _create_progress_bar(
    # pyre-ignore: Invalid type parameters [24]
    dataloader: Iterable,
    *,
    desc: str,
    num_epochs_completed: int,
    num_steps_completed: int,
    max_steps: Optional[int],
    max_steps_per_epoch: Optional[int],
) -> Optional[tqdm]:
    if not get_global_rank() == 0:
        return None

    current_epoch = num_epochs_completed
    total = _estimated_steps_in_epoch(
        dataloader,
        num_steps_completed=num_steps_completed,
        max_steps=max_steps,
        max_steps_per_epoch=max_steps_per_epoch,
    )
    return tqdm(desc=f"{desc} {current_epoch}", total=total)


def _update_progress_bar(
    progress_bar: tqdm, num_steps_completed: int, refresh_rate: int
) -> None:
    if not get_global_rank() == 0:
        return

    if (num_steps_completed + 1) % refresh_rate == 0:
        progress_bar.update(refresh_rate)


def _close_progress_bar(
    progress_bar: tqdm, num_steps_completed: int, refresh_rate: int
) -> None:
    if not get_global_rank() == 0:
        return

    progress_bar.update(
        num_steps_completed % refresh_rate
    )  # complete remaining progress in bar
    progress_bar.close()


def _estimated_steps_in_epoch(
    # pyre-ignore: Invalid type parameters [24]
    dataloader: Iterable,
    *,
    num_steps_completed: int,
    max_steps: Optional[int],
    max_steps_per_epoch: Optional[int],
) -> float:
    """estimate number of steps in current epoch for tqdm"""

    total = float("inf")
    if isinstance(dataloader, Sized):
        total = len(dataloader)

    if max_steps_per_epoch and max_steps:
        total = min(total, max_steps_per_epoch, max_steps - num_steps_completed)
    elif max_steps:
        total = min(total, max_steps - num_steps_completed)
    elif max_steps_per_epoch:
        total = min(total, max_steps_per_epoch)
    return total
