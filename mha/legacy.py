### Code copied from https://github.com/piomonti/MHA/blob/master/MHA_backend.py

from nilearn import plotting
import numpy as np
from tqdm import tqdm


def ProjectNonNegative(W):
    """
    projection onto the non-negative orthant
    """

    return W * (W > 0)


def ProjectMax1(W):
    """# BUG: this function changes the value of its input!!!!!
    project onto set of non-neg matricies with one nonzero entry per row
    """
    for i in range(W.shape[0]):
        max_id = W[i, :].argmax()
        W[i, :][np.where(W[i, :] < W[i, max_id])[0]] = 0
        W[i, max_id] = max(0, W[i, max_id])

    return W


def normalizeColumns(W):
    """
    standardize columns of W to be unit norm
    """
    for i in range(W.shape[1]):
        W[:, i] /= np.linalg.norm(W[:, i]) + 0.001

    return W


def AupdateDiag(W, EmpCov):
    """
    update A matrix assuming latent variables have diagonal covariance structure
    """

    targets = np.diag(W.T.dot(EmpCov).dot(W))
    Anew = np.eye(W.shape[1]) - np.diag(1.0 / targets)

    return Anew


def AupdateNonDiag(W, EmpCov):
    """
    update A matrix without assuming latent variables have diagonal covariance structure
    """

    invMat = np.linalg.pinv(W.T.dot(EmpCov).dot(W))
    Anew = np.eye(W.shape[1]) - invMat

    # TODO: figure out why he checks for positive eigenvals
    if np.min(np.linalg.eig(Anew)[0]) <= 0:
        Anew += np.eye(W.shape[1]) * (np.abs(np.min(np.linalg.eig(Anew)[0])) + 0.001)

    return Anew


def armijoUpdateW_MultiSubject_penalized(
    W, Wgrad, Gtilde, Shat, alpha=0.5, c=0.001, useStiefel=False, maxIter=1000
):
    """
    update projection matrix, W, using armijo backtracking
    """
    nSub = len(Shat)
    stopBackTracking = False
    Wgrad = normalizeColumns(Wgrad)
    iterCount = 0

    while stopBackTracking == False:
        if useStiefel:  # TODO: figure out what stiefiel does
            Wnew = W - alpha * (Wgrad - W.dot(Wgrad.T).dot(W))
        else:
            Wnew = W - alpha * Wgrad

        Wnew = ProjectNonNegative(Wnew)
        Wnew = normalizeColumns(
            Wnew
        )  # TODO: is normalizing and projecting necessary here?

        currObj = 0
        newObj = 0
        for i in range(nSub):  # TODO: what is this obj??
            currObj += np.diag(W.T.dot(Shat[i]).dot(W).dot(Gtilde[i])).sum()
            newObj += np.diag(Wnew.T.dot(Shat[i]).dot(Wnew).dot(Gtilde[i])).sum()

        if newObj <= currObj + c * alpha * (
            np.diag(np.diag(Wgrad.T.dot(Wnew - W))).sum() + 0.001
        ):
            stopBackTracking = (
                True  # TODO: why the center diag and the 0.001 and the Wnew-W
            )
        else:
            alpha /= 2
            iterCount += 1
            if iterCount > maxIter:
                stopBackTracking = True

    return Wnew


def nonNegativeCovFactor_LagrangeMult(
    Shat, k=2, diagG=False, lagParam=1, tol=0.01, alphaArmijo=0.5, maxIter=1000, verbose=False
):
    """
    INPUT:
            - Shat: list with each entry a square covariance matrix (np array)
            - k: rank of approximation (dimensionality of latent variables)
            - diagG: should latent variables have diagonal covariance structure
            - lagParam: coefficient for augmented lagrangian
            - alphaArmijo: backtracking parameter for Armijo rule
            - maxIter: max number of iterations
    OUTPUT:
            - W: non-negative orthonormal loading matrix
            - G: list, each entry a square latent variable covariance (np array)
            - iter: number of iterations

    the model proposed by Monti & Hyvarinen (2018) is as follows:
            - we have observations X_1, \ldots, X_n which following a zero mean Gaussian with covariance \Sigma
            - we model \Sigma = W G W^T + I for orthonormal W of rank K and dense G (k by k)
            - we propose to learn W and G via score matching with some constraints on W
            - we introduce non-negativity and orthonormality constraints on W in order to ensure the model is identifiable.
            - we note that directly optimizing over the set of non-neg orthonormal matricies is too difficult (depends very highly
            on the initial choice of W!). As a result, we employ augmented Lagragian multipliers and enforce orthonormality only
            in the limit (non-negativity is enforced at each iteration)
    """

    # define initial parameters:
    p = Shat[0].shape[0]
    nSub = len(Shat)
    ShatMean = np.zeros((p, p))  # mean covariance across all subjects
    for i in range(nSub):
        ShatMean += (1.0 / nSub) * Shat[i]
    LagMult = np.zeros((k, k))

    # initialize W to eigenvalues of ShatMean
    evdShat = np.linalg.eig(ShatMean)
    W = evdShat[1][
        :, evdShat[0].argsort()[::-1][:k]
    ]  # np.linalg.eig( ShatMean )[1][ :, :k ]
    # check if we should flip the sign (as evectors are sign invariant)  TODO: is the sign flip necessary?
    for i in range(W.shape[1]):
        if np.sum(W[:, i]) < 0:
            W[:, i] *= -1
    W = np.real(W)

    # if verbose: print("Initializing W ...");
    # while 1:
    #     # generate a matrix with positive entries
    #     W = np.random.rand(p, k)
    #     # set all but the max entry to zero, per row
    #     W = ProjectMax1(W)
    #     if np.linalg.matrix_rank(W) == k:
    #         break  # we want W to be full rank
    # W = normalizeColumns(W)

    # define convergence checks
    Wold = np.copy(W)
    W = ProjectNonNegative(W)

    # define A matrices (related to latent var covariances)
    if diagG:
        A = [AupdateDiag(W, Shat[i]) for i in range(nSub)]
    else:
        A = [AupdateNonDiag(W, Shat[i]) for i in range(nSub)]

    cArmijo = 0.01

    iterator = range(maxIter)
    if verbose:
        print("Optimizing...")
        iterator = tqdm(iterator)
    for iter_ in range(maxIter):
        # -------- update W matrix --------
        # print(iter_)
        # first compute Atilde
        AtildeAll = [0.5 * Amat.dot(Amat) - Amat for Amat in A]
        # compute gradient of SM objective with respect to W
        Wgrad = np.zeros(W.shape)
        for i in range(nSub):
            # print(i, Shat[i].dtype)
            Wgrad += Shat[i].dot(W).dot(AtildeAll[i])  # TODO: why divide by N?
        Wgrad += lagParam * (W.dot(W.T).dot(W) - W) + W.dot(LagMult)
        # compute armijo update:
        W = armijoUpdateW_MultiSubject_penalized(
            W=W,
            Wgrad=Wgrad,
            Gtilde=AtildeAll,
            Shat=Shat,
            alpha=alphaArmijo,
            c=cArmijo,
            useStiefel=False,
        )
        W = ProjectNonNegative(W)  # to ensure non-negativity
        W = normalizeColumns(W)

        # -------- update A matrices --------
        if diagG:
            A = [
                AupdateDiag(normalizeColumns(ProjectMax1(W)), Shat[i])
                for i in range(nSub)
            ]
        else:
            A = [
                AupdateNonDiag(normalizeColumns(ProjectMax1(W)), Shat[i])
                for i in range(nSub)
            ]

        # -------- update Lagrange multipler --------
        LagMult = LagMult + lagParam * (W.T.dot(W) - np.eye(k))

        # -------- check for convergence --------
        if np.sum(np.abs(W - Wold)) < tol:
            break
        else:
            Wold = np.copy(W)

    # compute final matrices
    W = normalizeColumns(ProjectMax1(W))
    # compute G (latent variable covariances)
    if diagG:
        G = [np.diag(np.diag(W.T.dot(Shat[i]).dot(W))) - np.eye(k) for i in range(nSub)]
    else:
        G = [W.T.dot(Shat[i]).dot(W) - np.eye(k) for i in range(nSub)]

    return {"W": W, "G": G, "iter": iter_}


class MHA:
    """
    class for MHA object
    INPUT:
            -
    """

    def __init__(self, Shat, k, diagG=False, verbose=False):
        self.Shat = Shat
        self.k = k
        self.diagG = diagG
        self.W = None
        self.G = None
        self.iter = None
        self.verbose = verbose

    def __repr__(self):
        mes = "MHA object\n"
        mes += "Number of subjects: " + str(len(self.Shat)) + "\n"
        mes += "Latent variable dim: " + str(self.k) + "\n"
        if self.diagG:
            mes += "Diagonal latent variable covariance"
        else:
            mes += "Full (ie non-diagonal) latent variable covariance"
        return mes

    def fit(self, lagParam=1, tol=0.01, alphaArmijo=0.5, maxIter=1000):
        """
        estimate loading matrix and latent variable covariances
        """
        res = nonNegativeCovFactor_LagrangeMult(
            Shat=self.Shat,
            k=self.k,
            diagG=self.diagG,
            lagParam=lagParam,
            tol=tol,
            alphaArmijo=alphaArmijo,
            maxIter=maxIter,
            verbose=self.verbose,
        )
        self.W = res["W"]
        self.G = res["G"]
        self.iter = res["iter"]

    def transform(self, Xnew):
        """
        apply projection matrix, W, to new data
        INPUT:
                - Xnew: list of numpy array, each entry should be an n by p array of n observations for p random variables
        """

        ProjXnew = [X.dot(self.W) for X in Xnew]
        return ProjXnew

    def plot(self, ROIcoord, clusterID, title):
        """
        INPUT:
                - ROIcoord: MNNI coordinates
                - clusterID: which cluster should we plot
        """
        ii = np.where(self.W[:, clusterID] != 0)[0]
        RandomMat = np.cov(
            np.random.random((10, len(ii))).T
        )  # this is just a place holder, we will not plot any of it!

        # we just plot the result
        plotting.plot_connectome(
            RandomMat,
            ROIcoord[ii, :],
            node_color="black",
            annotate=False,
            display_mode="ortho",
            edge_kwargs={"alpha": 0},
            node_size=50,
            title=title,
        )
