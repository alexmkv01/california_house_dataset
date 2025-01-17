import pickle
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
import os
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from torchvision import datasets, transforms
import torch.nn.functional as F
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
import matplotlib.pyplot as plt
from torch.optim.lr_scheduler import StepLR
from sklearn.model_selection import GridSearchCV

device = "cuda" if torch.cuda.is_available() else "cpu"

class Net(nn.Module):
    def __init__(self, neurons):
        self.layers = []
        super().__init__()

        for i in range(len(neurons)-1):
            self.layers.append(nn.Linear(neurons[i], neurons[i+1]))
            self.layers.append(nn.ReLU())
            
        self.linear_stack = nn.Sequential(*self.layers)

    def forward(self, x):
        # x = x.to(device)
        output = self.linear_stack(x)
        return output


class Regressor():

    def __init__(self, x, nb_epoch=200, lr=0.2, bs=64, neurons=[32,64]):
        """ 
        Initialise the model.
          
        Arguments:
            - x {pd.DataFrame} -- Raw input data of shape 
                (batch_size, input_size), used to compute the size 
                of the network.
            - nb_epoch {int} -- number of epochs to train the network.
            -- add new 

        """

        # You can add any input parameters you need
        # Remember to set them with a default value for LabTS tests

        # Constants used for normalising the numerical features.
      
        self.mean = None
        self.median_values = None
        self.std = None
        self.columns = None
        self.mode = None
        self.x = x

        self.learning_rate = lr
        self.nb_epoch = nb_epoch
        self.batch_size = bs
        self.neurons = neurons

        # Call preprocessor to get shape of cleaned data.
        X, _ = self._preprocessor(x, training = True)

        # eventually add number of layers, and dimensions of neurons for hyperparam tuning
        self.input_size = X.shape[1]
        self.output_size = 1

        self.neurons.insert(0, self.input_size)
        self.neurons.append(self.output_size)

        self.model = Net(neurons = self.neurons)
        # self.model = self.model.to(device)
 
        return


    def _preprocessor(self, x, y = None, training = False):
        """ 
        Preprocess input of the network.
          
        Arguments:
            - x {pd.DataFrame} -- Raw input array of shape 
                (batch_size, input_size).
            - y {pd.DataFrame} -- Raw target array of shape (batch_size, 1).
            - training {boolean} -- Boolean indicating if we are training or 
                testing the model.

        Returns:
            - {torch.tensor} or {numpy.ndarray} -- Preprocessed input array of
              size (batch_size, input_size). The input_size does not have to be the same as the input_size for x above.
            - {torch.tensor} or {numpy964.ndarray} -- Preprocessed target array of
              size (batch_size, 1).
            
        """
        # x consists of training data. Preprocess.
        if training:

            # Separate numerical and categorical Columns.
            x_without_ocean_proximity = x.drop('ocean_proximity', axis=1)

            # Fill missing numerical values with median + normalize
            self.mean = x_without_ocean_proximity.mean()
            self.std = x_without_ocean_proximity.std()
            self.median_values = x_without_ocean_proximity.median()

            x_without_ocean_proximity = x_without_ocean_proximity.fillna(self.median_values)
            x_without_ocean_proximity = (x_without_ocean_proximity - self.mean) / self.std

            # Fill missing categorical values with mode 
            self.mode = x['ocean_proximity'].mode()
            x['ocean_proximity'].fillna(self.mode, inplace=True)
            one_hot_encoded_ocean_proximities = pd.get_dummies(x['ocean_proximity'])

            # Concatenate one-hot encoded columns and numerical
            x = pd.concat([x_without_ocean_proximity, one_hot_encoded_ocean_proximities], axis=1)

            # Save the column headers (ensuring the test dataset has the same columns)
            self.columns = list(x.columns.values)

        else:
            
            # Separate Numerical and Categorical Columns.
            x_without_ocean_proximity = x.drop('ocean_proximity', axis=1)

            # Fill missing numerical values with median + normalize
            x_without_ocean_proximity = x_without_ocean_proximity.fillna(self.median_values)
            x_without_ocean_proximity = (x_without_ocean_proximity - self.mean) / self.std

            # Fill missing categorical values with mode 
            x['ocean_proximity'].fillna(self.mode, inplace=True)
            one_hot_encoded_ocean_proximities = pd.get_dummies(x['ocean_proximity'])

            # Concatenate one-hot encoded columns and numerical
            x = pd.concat([x_without_ocean_proximity, one_hot_encoded_ocean_proximities], axis=1)

            differences = list(set(self.columns) - set(x.columns.values))

            for col in differences:
                x[col]= 0

            # Save the column headers (ensuring the test dataset has the same columns)
            x = x[self.columns]

        # Convert training data and associated labels to tensors.
        x = torch.tensor(x.values, dtype=torch.float32)
        y = None if y is None else torch.tensor(y.values, dtype=torch.float32)

        # Return preprocessed x and y, return None for y if it was None
        return x, y

        
    def fit(self, x, y):
        """
        Regressor training function

        Arguments:
            - x {pd.DataFrame} -- Raw input array of shape 
                (batch_size, input_size).
            - y {pd.DataFrame} -- Raw output array of shape (batch_size, 1).

        Returns:
            self {Regressor} -- Trained model.

        """

        # Separate training data (90% of full dataset) to give us a total 80% train, 10% test, 10% val split.
        # x_train, x_val, y_train, y_val = train_test_split(x, y, random_state=3, test_size=0.1, shuffle=False)
        x_train = x
        y_train = y

        # Preprocess training and validation data.
        x_train, y_train = self._preprocessor(x_train, y_train, training = True) 

        # Combine the training set and training label tensors into a single tensor object.
        train_set = TensorDataset(x_train, y_train)

        # Batch (already shuffled) data.
        train_loader = torch.utils.data.DataLoader(train_set, batch_size=self.batch_size, shuffle=False, num_workers=4) 

        # Use stochastic gradient descent optimiser.
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)
        
        # scheduler = StepLR(optimizer, step_size=25, gamma=0.8)
        criterion = nn.MSELoss()

        training_losses = []
        # val_losses = []

        # Loop for given number of epochs
        for epoch in range(self.nb_epoch):  

            running_loss = 0

            # Execute learning cycle for all batches.
            self.model.train()
            for i, data in enumerate(train_loader):
                
                # Zero the parameter gradients
                optimizer.zero_grad()

                # Compute the model output over all inputs in this batch.
                inputs, labels = data
                # inputs = inputs.to(device)
                # labels = labels.to(device)
                predictions = self.model(inputs)

                # Compute the MSE loss between the model outputs and labels
                RMSE_loss = torch.sqrt(criterion(predictions, labels))
                running_loss += RMSE_loss.item()

                # Backpropagate the gradients.
                RMSE_loss.backward()
                optimizer.step()

            training_loss = running_loss / len(train_loader) # loss on last batch
            #if scheduler.get_last_lr()[0] > 0.001:
            #  scheduler.step()

            training_losses.append(training_loss)

            #self.model.eval()
            #val_loss = self.score(x_val, y_val)
            #val_losses.append(val_loss)

            
            if epoch % 20 == 19 or epoch==0:
                print("epoch: {}, training loss: {}".format(epoch+1, training_loss))
                #print("epoch: {}, validation loss: {}".format(epoch+1, val_loss))
                #print("epoch: {}, learning rate: {}".format(epoch+1, scheduler.get_last_lr()[0]))
                print()
                # pass
        
        # plot_learning_curve(training_losses, val_losses)        
        return self

            
    def predict(self, x):
        """
        Output the value corresponding to an input x.

        Arguments:
            x {pd.DataFrame} -- Raw input array of shape 
                (batch_size, input_size).

        Returns:
            {np.ndarray} -- Predicted value for the given input (batch_size, 1).

        """

        x, _ = self._preprocessor(x, training = False) # Do not forget
        # x = x.to(device)
        predictions = []
        for i, row in enumerate(x):
            prediction = self.model(row)
            predictions.append(prediction.item())

        n = len(predictions)
        predictions = np.array(predictions).reshape(n,1)
        return predictions
    
    def get_params(self, deep=True):
      params = {
          "x": self.x,
          "nb_epoch": self.nb_epoch,
          "lr": self.learning_rate,
          "bs": self.batch_size,
          "neurons": self.neurons    
      }
      return params
    
    def set_params(self, **parameters):
      return Regressor(self.x, **parameters)
    
    def mean_absolute_difference(self, x,y):
        X, Y_gold = self._preprocessor(x, y = y, training = False) 
        predictions = []
        for i, row in enumerate(X):
            prediction = self.model(row)
            predictions.append(prediction.item())

        n = len(predictions)
        Ｙ＿predict = np.array(predictions).reshape(n,1)
        error = (mean_absolute_error(Y_gold, Y_predict))
        return error

    def score(self, x, y):
        """
        Function to evaluate the model accuracy on a validation dataset.

        Arguments:
            - x {pd.DataFrame} -- Raw input array of shape 
                (batch_size, input_size).
            - y {pd.DataFrame} -- Raw output array of shape (batch_size, 1).

        Returns:
            {float} -- Quantification of the efficiency of the model.

        """

        X, Y_gold = self._preprocessor(x, y = y, training = False) 
        # X = X.to(device)
        # Y_gold = Y_gold.to(device)
        predictions = []
        for i, row in enumerate(X):
            prediction = self.model(row)
            predictions.append(prediction.item())

        n = len(predictions)
        Ｙ＿predict = np.array(predictions).reshape(n,1)
        rmse = np.sqrt(mean_squared_error(Y_gold, Y_predict))
        return rmse # changed to negative for GridSearchCV. ACTION REQUIRED (change for submit)
    

    def r2_score(self, x, y):
        """
        Function to evaluate the model accuracy on a validation dataset.

        Arguments:
            - x {pd.DataFrame} -- Raw input array of shape 
                (batch_size, input_size).
            - y {pd.DataFrame} -- Raw output array of shape (batch_size, 1).

        Returns:
            {float} -- Quantification of the efficiency of the model.

        """

        X, Y_gold = self._preprocessor(x, y = y, training = False) 
        predictions = []
        for i, row in enumerate(X):
            prediction = self.model(row)
            predictions.append(prediction.item())

        n = len(predictions)
        Ｙ＿predict = np.array(predictions).reshape(n,1)
        r2 = r2_score(Y_gold, Y_predict)
         
        return r2 
    

def plot_learning_curve(training_errors, val_errors):
    assert(len(training_errors) == len(val_errors))
    plt.figure(figsize=(12,10))
    epochs = [i for i in range(len(training_errors))]
    plt.plot(epochs, training_errors)
    plt.plot(epochs, val_errors)
    plt.xlabel("Epochs")
    plt.ylabel("RMSE")
    plt.legend(["Training", "Validation"])
    plt.title("Training Curve")
    plt.show()
    return

def save_regressor(trained_model): 
    """  Utility function to save the trained regressor model in part2_model.pickle.
    """

    # If you alter this, make sure it works in tandem with load_regressor
    with open('part2_model.pickle', 'wb') as target:
        pickle.dump(trained_model, target)
    print("\nSaved model in part2_model.pickle\n")


def load_regressor(): 
    """  Utility function to load the trained regressor model in part2_model.pickle.
    """

    # If you alter this, make sure it works in tandem with save_regressor
    with open('part2_model.pickle', 'rb') as target:
        trained_model = pickle.load(target)
    print("\nLoaded model in part2_model.pickle\n")
    return trained_model


def RegressorHyperParameterSearch(x_train, y_train, config): 
    # Ensure to add whatever inputs you deem necessary to this function
    """
    Performs a hyper-parameter for fine-tuning the regressor implemented 
    in the Regressor class.

    Arguments:
        Add whatever inputs you need.
        
    Returns:
        The function should return your optimised hyper-parameters. 

    """
    regressor = Regressor(x_train)
    classifier = GridSearchCV(estimator = regressor, cv=5, param_grid = config, verbose=3, refit="neg_root_mean_squared_error", scoring=["neg_root_mean_squared_error", "r2"], return_train_score=True)
    classifier.fit(x_train, y_train)

    return classifier.cv_results



def example_main():

    output_label = "median_house_value"

    # Use pandas to read CSV data as it contains various object types
    # Feel free to use another CSV reader tool
    # But remember that LabTS tests take Pandas DataFrame as inputs
    data = pd.read_csv("housing.csv") 

    # Splitting input and output
    x = data.loc[:, data.columns != output_label]
    y = data.loc[:, [output_label]]
    x_train, x_test, y_train, y_test = train_test_split(x, y, random_state=3, train_size=0.9, shuffle=True)

    # search space
    config = {
        "nb_epoch": [100,200,300],
        "bs": [32],
        "lr": [0.1],
        "neurons": [[32], [16,32], [32,64], [16,32,64],
                    [32,64,32], [32,64,96,16], [32,64,96,32]]
    }

    """ Grid Search Hyperparam tuning
    grid_search_results = RegressorHyperParameterSearch(x_train, y_train, config)
    results_df = pd.DataFrame(grid_search_results)
    results_df.to_csv("grid_search_results.csv")
    """

    # Hyperparameters
    epochs = 200
    learning_rate = 0.2
    batch_size = 64
    hidden_neurons = [32,64]
    
    # regressor = Regressor(x)
    regressor = Regressor(x, nb_epoch=epochs, lr=learning_rate, bs=batch_size, neurons= hidden_neurons)
    regressor.fit(x_train, y_train)

    save_regressor(regressor)
    regressor = load_regressor()
    
    # Prediction on unseen test data
    rmse = regressor.score(x_test, y_test)
    r2_score = regressor.r2_score(x_test, y_test)
    absolute_diff = regressor.mean_absolute_difference(x_test, y_test)

    # Error
    print("\nRegressor RMSE: {}\n".format(rmse))
    print("Regressor r2 score: {}\n".format(r2_score))
    print("Mean Absolute Difference: {}\n".format(absolute_diff))
    print()


if __name__ == "__main__":
    example_main()
