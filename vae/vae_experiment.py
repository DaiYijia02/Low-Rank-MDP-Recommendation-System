import os
import math
import torch
from torch import optim
from vae import *
import pytorch_lightning as pl
# from torchvision import transforms
# import torchvision.utils as vutils
# from torchvision.datasets import CelebA
# from torch.utils.data import DataLoader


def data_loader(fn):
    """
    Decorator to handle the deprecation of data_loader from 0.7
    :param fn: User defined data loader function
    :return: A wrapper for the data_loader function
    """

    def func_wrapper(self):
        try:  # Works for version 0.6.0
            return pl.data_loader(fn)(self)

        except:  # Works for version > 0.6.0
            return fn(self)

    return func_wrapper


class VAEXperiment(pl.LightningModule):

    def __init__(self,
                 vae_model: VAE,
                 params: dict) -> None:
        super(VAEXperiment, self).__init__()

        self.model = vae_model
        self.params = params
        self.curr_device = torch.device("cuda:0")
        try:
            self.hold_graph = self.params['retain_first_backpass']
        except:
            pass

    # def forward(self, input, **kwargs):
    #     return self.model(input, **kwargs)

    def forward(self, real_data):
        return self.model(real_data)

    def training_step(self, batch, batch_idx, optimizer_idx=0):
        real_data, labels = batch

        z_mean, z_log_var, encoded, decoded = self.forward(
            real_data)
        train_loss = self.model.loss_function(z_mean, z_log_var, encoded, decoded, real_data, labels,
                                              M_N=self.params['kld_weight'],
                                              optimizer_idx=optimizer_idx,
                                              batch_idx=batch_idx)

        self.log_dict({key: val.item()
                      for key, val in train_loss.items()}, sync_dist=True)

        return train_loss['loss']

    def validation_step(self, batch, batch_idx, optimizer_idx=0):
        real_data, labels = batch

        z_mean, z_log_var, encoded, decoded = self.forward(
            real_data)
        val_loss = self.model.loss_function(z_mean, z_log_var, encoded, decoded, real_data, labels,
                                            M_N=1.0,
                                            optimizer_idx=optimizer_idx,
                                            batch_idx=batch_idx)

        self.log_dict({f"val_{key}": val.item()
                      for key, val in val_loss.items()}, sync_dist=True)

    def on_validation_end(self) -> None:
        self.sample_images()

    def sample_images(self):
        # Get sample reconstruction image
        test_input, test_label = next(
            iter(self.trainer.datamodule.test_dataloader()))
        test_input = test_input.to(self.curr_device)
        test_label = test_label.to(self.curr_device)

#         test_input, test_label = batch
        recons = self.model.generate(test_input, labels=test_label)
        # vutils.save_image(recons.data,
        #                   os.path.join(self.logger.log_dir,
        #                                "Reconstructions",
        #                                f"recons_{self.logger.name}_Epoch_{self.current_epoch}.png"),
        #                   normalize=True,
        #                   nrow=12)
        print("Should save sample here")

        try:
            samples = self.model.sample(144,
                                        self.curr_device,
                                        labels=test_label)
            # vutils.save_image(samples.cpu().data,
            #                   os.path.join(self.logger.log_dir,
            #                                "Samples",
            #                                f"{self.logger.name}_Epoch_{self.current_epoch}.png"),
            #                   normalize=True,
            #                   nrow=12)
            print("Should save sample here")
        except Warning:
            pass

    def configure_optimizers(self):

        optims = []
        scheds = []

        optimizer = optim.Adam(self.model.parameters(),
                               lr=self.params['LR'],
                               weight_decay=self.params['weight_decay'])
        optims.append(optimizer)
        # Check if more than 1 optimizer is required (Used for adversarial training)
        try:
            if self.params['LR_2'] is not None:
                optimizer2 = optim.Adam(getattr(self.model, self.params['submodel']).parameters(),
                                        lr=self.params['LR_2'])
                optims.append(optimizer2)
        except:
            pass

        try:
            if self.params['scheduler_gamma'] is not None:
                scheduler = optim.lr_scheduler.ExponentialLR(optims[0],
                                                             gamma=self.params['scheduler_gamma'])
                scheds.append(scheduler)

                # Check if another scheduler is required for the second optimizer
                try:
                    if self.params['scheduler_gamma_2'] is not None:
                        scheduler2 = optim.lr_scheduler.ExponentialLR(optims[1],
                                                                      gamma=self.params['scheduler_gamma_2'])
                        scheds.append(scheduler2)
                except:
                    pass
                return optims, scheds
        except:
            return optims
