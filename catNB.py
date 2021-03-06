import pandas as pd
import numpy as np

# NOTE: this is a preliminary version that uses nested dictionaries and for-loops
# rather than arrays and matrix multiplication.  This makes it a little slow.
# Vectorizing is a little complicated and require scipy's sparse matrices
# because the dimensions of each column are different (for instance, the dataset
# for which I built this had 3500 categorical values for one feature). For now,
# consider it a work in progress.

class CatNB():
    def __init__(self):
        self.feature_count = 0
        self.train_example_count = 0
        self.column_names = []
        self.max_class_prob = (None, 0)
        self.class_labels = []
        self.class_priors = {} # dictionary of prior probabilities for every
                                # target category

        self.feature_priors = {} # a nested dict that will contain one dictionary
                                 # per feature, with each dictionary containing
                                 # the prior prob for each value of that feature

        # self.conditional_probs = pd.DataFrame # each column is a feature,
        #                                       # each row is a target class,
        #                                       # and each cell holds a dictionary
        #                                       # of the conditional probability
        #                                       # for each value of that feature
        #                                       # given the target class

        self.conditional_probs = {} # triple-nested dict:
                                    # class-->column-->value

    def fit(self, X, y):
        '''
        X: a pandas dataframe (or array-like type convertible to pandas DataFrame object)
        y: a pandas series (or series-like type convertible to pandas Series object)
        '''
        # handle dtype errors
        if type(y) != pd.core.series.Series:
            try:
                y = pd.Series(y)
            except:
                return TypeError("y must be a pandas Series or convertible type")
        if y.dtype == np.dtype('float'):
            raise TypeError("target column must be str, bool, or int")
        if type(X) != pd.core.frame.DataFrame:
            try:
                X = pd.DataFrame(X)
            except:
                return TypeError("X must be a pandas dataframe or convertible type")
        for col in X.columns:
            if X[col].dtype != np.dtype('object'):
                raise TypeError("X dataframe may only contain dtype 'object' ")
        X = X.fillna('Nulll_as_cat') # extra l to avoid overlap with existing values

        # set feature count & column names
        self.train_example_count = X.shape[0]
        self.feature_count = X.shape[1]
        self.column_names = X.columns
        self.class_labels = y.unique()
        # extract and store feature-priors information from y
        target_class_counts = y.value_counts()
        for target_class in y.unique():
            prior = target_class_counts[target_class] / y.shape[0]
            self.class_priors[target_class] = prior
            if prior > self.max_class_prob[1]:
                self.max_class_prob = (target_class, prior)
        # extract and store information from X
        for col in X.columns:
            # store priors for each category value:
            priors_dict = {}
            col_val_counts = X[col].value_counts()
            for val in X[col].unique():
                priors_dict[val] = col_val_counts[val] / X.shape[0]
            self.feature_priors[col] = priors_dict
        # extract and store class-conditional probabilities:
        for target_class in y.unique():
            self.conditional_probs[target_class] = {}
            for col in X.columns:
                self.conditional_probs[target_class][col] = {}
        for target_class in y.unique():
            X_yval = X[y==target_class]
            for col in X_yval.columns:
                probs_dict = {}
                col_val_counts = X_yval[col].value_counts()
                for val in X_yval[col].unique():
                    probs_dict[val] = col_val_counts[val] / X_yval.shape[0]
                self.conditional_probs[target_class][col] = probs_dict

    def predict(self, X, return_probs=False, null_as_cat=False):
        '''
        Args:
            X: a pandas dataframe
            return_probs: boolean
        Returns:
            [with return_probs=False]: list of predicted class for each row in X
            [with return_probs=True]: tuple (predictions, probabilities), where
                - predictions = list of predicted class for each row in X
                - probabilities = list of probability of predicted class for each row in X
        '''
        # handle dtype errors:
        if type(X) != pd.core.frame.DataFrame:
            try:
                X = pd.DataFrame(X)
            except:
                return TypeError("X must be a pandas dataframe or convertible type")
        for col in X.columns:
            if X[col].dtype != np.dtype('object'):
                raise TypeError("X dataframe may only contain dtype 'object' ")
        # handle shape error:
        if X.shape[1] != self.feature_count:
            return ValueError("X does not have same number of features as training frame")
        # handle different-columns error:
        if (X.columns != self.column_names).any():
            return ValueError("X does not have the same columns as training frame")

        # initiate probabilities and predictions lists:
        probabilities = []
        predictions = []

        # define helper function that gets the probability for one row for one
        # target class
        def get_one_proba(row,
                        col_names,
                        target_class,
                        class_priors,
                        feature_priors,
                        conditional_probs,
                        train_row_count,
                        test_row_count):
            # access target-value prior:
            target_class_prior = class_priors[target_class]

            # calculate total feature-vector prior
            # and total conditional feture_vector probability:
            ft_vector_prior = 1
            ft_vector_conditional = 1
            for col, val in zip(col_names, row):
                # first deal with the exceptional case where row contains a new value
                # not seen in the training set:
                if null_as_cat == False:
                    if val == 'Nulll_as_cat':
                        break
                # check to make sure this feature value occurred in training set:
                if val not in feature_priors[col].keys():
                    # assume it's the only instance in all train and test data and
                    # set prior to 1 / (num_x_train + num_x_test)
                    prior = 1 / (train_row_count + test_row_count)
                    # assuming it's the only instance means that the conditional
                    # probability is 1 / all occurrences of target val
                    cond_prob = 1 / (target_class_prior * (train_row_count + test_row_count))
                # check to make sure this feature value occurred for this class
                # in the training set:
                elif val not in conditional_probs[target_class][col].keys():
                    cond_prob = 1 / (target_class_prior * (train_row_count + test_row_count))
                    prior = feature_priors[col][val]
                # treat the normal case:
                else:
                    prior = feature_priors[col][val]
                    cond_prob = conditional_probs[target_class][col][val]
                # short-circuit function if conditional probability is 0:
                if cond_prob == 0:
                    return 0
                # otherwise, update feature vector probabilities
                ft_vector_prior *= prior
                ft_vector_conditional *= cond_prob

            return ft_vector_conditional * target_class_prior / ft_vector_prior

        # define helper function that gets prediction and associated probability
        # for one row / example
        def get_pred_proba(row,
                        col_names,
                        target_classes,
                        class_priors,
                        feature_priors,
                        conditional_probs,
                        train_row_count,
                        test_row_count):
            max_prob = 0
            pred_class = None
            for target_class in target_classes:
                prob = get_one_proba(row,
                                col_names,
                                target_class,
                                class_priors,
                                feature_priors,
                                conditional_probs,
                                train_row_count,
                                test_row_count)
                if prob > max_prob:
                    max_prob = prob
                    pred_class = target_class
            # deal with extremely rare case where all conditional probabilities
            # are 0 (results if for each target category there is at least one
            # value in this row that never occurred with that target)
            if pred_class == None:
                print("Error: a row has at least one new value for every class.")
                print("This being the case, the most common class has been predicted.")
                pred_class = max_class_prob[0]
                max_prob = max_class_prior[1]
            return pred_class, max_prob

        # calculate probabilities for each row:
        for index, row in X.iterrows():
            prediction, probability = get_pred_proba(row,
                            self.column_names,
                            self.class_labels,
                            self.class_priors,
                            self.feature_priors,
                            self.conditional_probs,
                            self.train_example_count,
                            X.shape[0])
            predictions.append(prediction)
            probabilities.append(probability)

        if return_probs:
            return (predictions, probabilities)
        else:
            return predictions


        # # ALT METHOD: calculate prior-probability vectors for all feature vectors
        # # (disadvantage: it can't short-circuit as soon as one prob is 0
        # priors_df = X.copy
        # for col in X.columns:
        #     priors_df[col] = priors_df[col].apply(lambda x: self.feature_priors[col][x])


    def predict_proba(self, X):
        '''
        X: a pandas dataframe
        '''
        return predict(X, return_probs=True)[1]
