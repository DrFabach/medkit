import pytest

torch = pytest.importorskip(modname="torch", reason="torch is not installed")

from medkit.training import TrainerConfig, Trainer  # noqa: E402
from medkit.training.trainer import (
    OPTIMIZER_NAME,
    CONFIG_NAME,
    SCHEDULER_NAME,
)  # noqa: E402

from .dummy_context_component.dummy_corpus import DUMMY_DATASETS  # noqa: E402
from .dummy_context_component.dummy_component import (
    MockTrainableComponent,
)  # noqa: E402


class DummyMetricsComputer:
    def prepare_batch(self, model_output, input_batch):
        predictions = model_output["logits"].argmax(1).detach()
        references = input_batch["labels"].detach()
        return {"predictions": predictions, "references": references}

    def compute(self, all_data):
        predictions = torch.tensor(all_data["predictions"])
        references = torch.tensor(all_data["references"])

        TP = (predictions == references).sum().item()
        score = TP / len(predictions)
        return {"acc": score}


TEST_METRICS = [
    (None, False, ["loss"], ["loss"]),
    (DummyMetricsComputer(), False, ["loss"], ["loss", "acc"]),
    (DummyMetricsComputer(), True, ["loss", "acc"], ["loss", "acc"]),
]


@pytest.mark.parametrize(
    "metrics_computer,do_metrics_in_training,expected_train_metrics,expected_eval_metrics",
    TEST_METRICS,
    ids=["default_metrics", "more_metrics_in_eval", "more_metrics_train_eval"],
)
def test_trainer_with_metrics(
    tmp_path,
    metrics_computer,
    do_metrics_in_training,
    expected_train_metrics,
    expected_eval_metrics,
):
    mock_component = MockTrainableComponent()
    output_dir = tmp_path / "dummy-operation"
    config = TrainerConfig(
        output_dir=output_dir,
        batch_size=1,
        do_metrics_in_training=do_metrics_in_training,
        seed=0,
    )
    trainer = Trainer(
        mock_component,
        config=config,
        train_data=DUMMY_DATASETS["train"],
        eval_data=DUMMY_DATASETS["eval"],
        metrics_computer=metrics_computer,
    )
    log_history = trainer.train()

    # check metrics per epoch
    assert len(log_history) == config.nb_training_epochs
    metrics_epoch_0 = log_history[0]
    assert list(metrics_epoch_0["train"].keys()) == expected_train_metrics
    assert list(metrics_epoch_0["eval"].keys()) == expected_eval_metrics


TEST_SCHEDULER = [
    (None, "loss"),
    (
        lambda optimizer: torch.optim.lr_scheduler.StepLR(
            optimizer, step_size=1, gamma=0.1
        ),
        "loss",
    ),
    (
        lambda optimizer: torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, "max"),
        "acc",
    ),
    (
        lambda optimizer: torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, "max"),
        "f1_score",
    ),
]


@pytest.mark.parametrize(
    "lr_scheduler_builder,metric_to_track_lr",
    TEST_SCHEDULER,
    ids=[
        "default_no_lr_scheduler",
        "lr_sch_step",
        "lr_sch_reduceLR_valid_metric",
        "lr_sch_reduceLR_unk_metric",
    ],
)
def test_trainer_with_lr_scheduler(tmp_path, lr_scheduler_builder, metric_to_track_lr):
    mock_component = MockTrainableComponent()
    output_dir = tmp_path / "dummy-operation"
    config = TrainerConfig(
        output_dir=output_dir,
        batch_size=1,
        metric_to_track_lr=metric_to_track_lr,
        seed=0,
    )
    trainer = Trainer(
        mock_component,
        config=config,
        train_data=DUMMY_DATASETS["train"],
        eval_data=DUMMY_DATASETS["eval"],
        lr_scheduler_builder=lr_scheduler_builder,
        metrics_computer=DummyMetricsComputer(),
    )

    if metric_to_track_lr != "f1_score":
        trainer.train()

    else:
        with pytest.raises(
            ValueError, match="Learning scheduler needs an eval metric to update .*"
        ):
            trainer.train()


@pytest.mark.parametrize(
    "lr_scheduler_builder",
    [
        None,
        lambda optimizer: torch.optim.lr_scheduler.StepLR(
            optimizer, step_size=1, gamma=0.1
        ),
    ],
    ids=["default_no_lr_scheduler", "with_lr_scheduler"],
)
def test_trainer_checkpoint(tmp_path, lr_scheduler_builder):
    mock_component = MockTrainableComponent()
    output_dir = tmp_path / "full_model"
    config = TrainerConfig(
        output_dir=output_dir,
        batch_size=1,
        seed=0,
    )
    trainer = Trainer(
        mock_component,
        config=config,
        train_data=DUMMY_DATASETS["train"],
        eval_data=DUMMY_DATASETS["eval"],
        lr_scheduler_builder=lr_scheduler_builder,
    )
    trainer.train()

    path_checkpoint = list(output_dir.iterdir())[0]
    expected_optimizer_file = path_checkpoint / OPTIMIZER_NAME
    expected_config_file = path_checkpoint / CONFIG_NAME
    expected_scheduler_file = path_checkpoint / SCHEDULER_NAME
    assert expected_optimizer_file.exists()
    assert expected_config_file.exists()

    if lr_scheduler_builder is not None:
        assert expected_scheduler_file.exists()
    else:
        assert not expected_scheduler_file.exists()

    # testing model checkpoint
    # this is related to trainable component
    MockTrainableComponent(model_path=path_checkpoint)
