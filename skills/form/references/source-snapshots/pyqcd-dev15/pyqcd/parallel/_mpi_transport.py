"""MPI 域分解搬运层（照抄 refer/sush/lqcddb base/mpi_init.py，自包含）。

覆盖：mpinit/initGrid/initDevice(numpy 路径)、getDefaultGrid 及其
_factorization/_composition/_partition、坐标↔秩映射（XYZT/TZYX 网格序）、
get_mpi_tlist(find/TScatter)、get_mpi_data 八模式
(Send/Gather/TGather/Allgather/Bcast/Scatter/TScatter/Transport)。
"""
from typing import Any, Dict, List, Literal, NamedTuple, Union

import numpy as np
from mpi4py import MPI


class _MPILogger:
    def __init__(self, root: int = 0) -> None:
        self.root = root

    def info(self, msg: str):
        pass

    def warning(self, msg: str, category: type = RuntimeWarning):
        pass

    def critical(self, msg: str, category: type = RuntimeError):
        raise category(msg)


_MPI_LOGGER = _MPILogger()
_MPI_COMM: MPI.Intracomm = MPI.COMM_WORLD
_MPI_SIZE: int = _MPI_COMM.Get_size()
_MPI_RANK: int = _MPI_COMM.Get_rank()
_GRID_SIZE: Union[List[int], None] = None
_GRID_COORD: Union[List[int], None] = None
_GRID_MAP: Literal["XYZT_FASTEST", "TZYX_FASTEST"] = "XYZT_FASTEST"
_BACKEND: Literal["numpy", "cupy", "torch"] = "numpy"
_CUDA_IS_HIP: bool = False
_CUDA_DEVICE: int = -1
_CUDA_COMPUTE_CAPABILITY = (0, 0)

_TAG_RESERVE: int = 30_000
_SEND_TAG_BASE: int = 0


def isGridInitialized() -> bool:
    return _GRID_SIZE is not None


def isDeviceInitialized() -> bool:
    return _CUDA_DEVICE >= 0


def getCUDABackend():
    return _BACKEND


def isCUDABackend() -> bool:
    return _BACKEND in ("cupy", "torch")


def isNumpyBackend() -> bool:
    return _BACKEND == "numpy"


def isHIP() -> bool:
    return _CUDA_IS_HIP


def getCUDADevice():
    return _CUDA_DEVICE


def getCUDAComputeCapability():
    return _CUDA_COMPUTE_CAPABILITY


def getMPIComm():
    return _MPI_COMM


def getMPISize():
    return _MPI_SIZE


def getMPIRank():
    return _MPI_RANK


def getGridSize():
    if _GRID_SIZE is None:
        raise RuntimeError("Grid is not initialized")
    return _GRID_SIZE


def getGridCoord():
    if _GRID_COORD is None:
        raise RuntimeError("Grid is not initialized")
    return _GRID_COORD


def getGridMap():
    return _GRID_MAP


def setGridMap(grid_map: Literal["XYZT_FASTEST", "TZYX_FASTEST"]):
    global _GRID_MAP
    _GRID_MAP = grid_map


def getRankFromCoord(grid_coord: List[int], grid_size: List[int] = None) -> int:
    def _process(xyzt):
        return xyzt[::-1] if _GRID_MAP == "TZYX_FASTEST" else xyzt

    gs = _process(_GRID_SIZE if grid_size is None else grid_size)
    gc = _process(grid_coord)
    mpi_rank = 0
    for g_, G in zip(gc, gs):
        mpi_rank = mpi_rank * G + g_
    return mpi_rank


def getCoordFromRank(mpi_rank: int, grid_size: List[int] = None) -> List[int]:
    def _process(xyzt):
        return xyzt[::-1] if _GRID_MAP == "XYZT_FASTEST" else xyzt

    if grid_size is None:
        assert isGridInitialized()
        gs = _process(_GRID_SIZE)
    else:
        gs = _process(grid_size)
    coord = []
    for G in gs:
        coord.append(mpi_rank % G)
        mpi_rank //= G
    return _process(coord)


def _composition(n: int, d: int):
    addend: List[List[int]] = []
    i = [0 for _ in range(d - 1)] + [n] + [0]
    while i[0] <= n:
        addend.append([i[s_] - i[s_ - 1] for s_ in range(d)])
        i[d - 2] += 1
        for s_ in range(d - 2, 0, -1):
            if i[s_] == n + 1:
                i[s_] = 0
                i[s_ - 1] += 1
        for s_ in range(1, d - 1, 1):
            if i[s_] < i[s_ - 1]:
                i[s_] = i[s_ - 1]
    return addend


def _factorization(k: int, d: int):
    prime_factor: List[List[List[int]]] = []
    for p_ in range(2, int(k ** 0.5) + 1):
        n = 0
        while k % p_ == 0:
            n += 1
            k //= p_
        if n != 0:
            prime_factor.append(
                [[p_ ** a for a in addend] for addend in _composition(n, d)])
    if k != 1:
        prime_factor.append([[k ** a for a in addend]
                             for addend in _composition(1, d)])
    return prime_factor


def _partition(factor: List[List[List[int]]], sublatt_size: List[int],
               grid_size: List[int] = None, idx: int = 0):
    if idx == 0:
        grid_size = [1 for _ in range(len(sublatt_size))]
        factor = _factorization(factor, len(sublatt_size))
    if idx == len(factor):
        yield grid_size
    else:
        for factor_size in factor[idx]:
            for L, x in zip(sublatt_size, factor_size):
                if L % x != 0:
                    break
            else:
                yield from _partition(
                    factor,
                    [L // f for L, f in zip(sublatt_size, factor_size)],
                    [G * f for G, f in zip(grid_size, factor_size)],
                    idx + 1,
                )


def getDefaultGrid(mpi_size: int, latt_size: List[int]):
    latt_vol = latt_size[0] * latt_size[1] * latt_size[2] * latt_size[3]
    latt_surf = [latt_vol // latt_size[d] for d in range(4)]
    min_comm, min_grid = latt_vol, []
    assert latt_vol % mpi_size == 0, \
        "lattice volume must be divisible by MPI size"
    partition = _partition(mpi_size, list(latt_size))
    for grid_size in partition:
        comm = [latt_surf[d] * grid_size[d] for d in range(4)
                if grid_size[d] > 1]
        if sum(comm) < min_comm:
            min_comm, min_grid = sum(comm), [grid_size]
        elif sum(comm) == min_comm:
            min_grid.append(grid_size)
    if not min_grid:
        raise ValueError(
            f"Cannot get proper grid for {latt_size} with {mpi_size} ranks")
    return min(min_grid)


def initGrid(grid_size: List[int] = None, latt_size: List[int] = None):
    global _GRID_SIZE, _GRID_COORD
    if _GRID_SIZE is None:
        if grid_size is None and latt_size is not None:
            grid_size = getDefaultGrid(_MPI_SIZE, latt_size)
        grid_size = grid_size if grid_size is not None else [1, 1, 1, 1]
        if _MPI_SIZE != grid_size[0] * grid_size[1] * grid_size[2] * grid_size[3]:
            raise ValueError(
                f"MPI size {_MPI_SIZE} != grid size {grid_size}")
        _GRID_SIZE = list(grid_size)
        _GRID_COORD = getCoordFromRank(_MPI_RANK, _GRID_SIZE)
    else:
        from warnings import warn
        warn("Grid is already initialized", RuntimeWarning)


def initDevice(backend: Literal["numpy", "cupy", "torch"] = "numpy",
               device: int = -1, enable_mps: bool = False,
               cuda_device_count: int = None):
    global _BACKEND, _CUDA_DEVICE
    if _CUDA_DEVICE < 0:
        _BACKEND = backend or "numpy"
        if _BACKEND == "numpy":
            _CUDA_DEVICE = 0 if cuda_device_count is None \
                and device >= 0 else device
            if _CUDA_DEVICE < 0:
                _CUDA_DEVICE = 0
        else:
            _CUDA_DEVICE = max(device, 0)


def mpinit(grid_size: List[int], latt_size: List[int] = None,
           backend: Literal["numpy", "cupy", "torch"] = "numpy",
           device: int = -1, enable_mps: bool = False,
           cuda_device_count: int = None):
    initDevice(backend=backend, device=device, enable_mps=enable_mps,
               cuda_device_count=cuda_device_count)
    initGrid(grid_size, latt_size=latt_size)


def get_mpi_tlist(Nt, t, gtype: Literal["find", "TScatter"] = "find"):
    """时间片→秩 映射（find）/ 秩内分配（TScatter），照抄参照。"""
    size = getMPISize()
    rank = getMPIRank()

    if gtype == "find":
        if isinstance(t, (int, float)):
            return int(t) % size, ((int(t) + Nt) % Nt) // size
        if isinstance(t, (list, range)):
            t_list = [x % Nt for x in t]
        else:
            t_list = [x % Nt for x in np.asarray(t).reshape(-1)]
        return ([x % size for x in t_list],
                [((x + Nt) % Nt) // size for x in t_list])

    if isinstance(t, (int, float)):
        t_list = [t % Nt]
    elif isinstance(t, (list, range)):
        t_list = [x % Nt for x in t]
    else:
        t_list = [x % Nt for x in np.asarray(t).reshape(-1)]

    t_list_rank = [x for x in t_list if x % size == rank]
    list_rank = [rank for x in t_list if x % size == rank]
    t_list_rank_indx = [((x - rank + Nt) % Nt) // size for x in t_list_rank]
    return t_list_rank, list_rank, t_list_rank_indx


def _next_send_tags():
    global _SEND_TAG_BASE
    _SEND_TAG_BASE = (_SEND_TAG_BASE + 3) % _TAG_RESERVE
    return _SEND_TAG_BASE, _SEND_TAG_BASE + 1, _SEND_TAG_BASE + 2


_VALID_MODES = frozenset({
    "Send", "Gather", "TGather", "Allgather",
    "Bcast", "Scatter", "TScatter", "Transport",
})


def get_mpi_data(data,
                 mdtype: Literal["Send", "Gather", "TGather", "Allgather",
                                 "Bcast", "Scatter", "TScatter",
                                 "Transport"] = "Gather",
                 root: int = 0, recv_rank: int = 0,
                 recv_buff=None, axis: int = 0):
    """MPI 数据搬运八模式（照抄参照，numpy 后端路径）。"""
    comm = getMPIComm()
    rank = comm.Get_rank()
    size = comm.Get_size()

    if mdtype not in _VALID_MODES:
        raise ValueError(f"Unknown mdtype {mdtype!r}")

    if size == 1:
        return data.copy() if hasattr(data, "copy") else data

    if mdtype == "Send":
        if recv_rank >= size:
            raise ValueError(f"recv_rank {recv_rank} >= size {size}")
        tag_d, tag_s, tag_t = _next_send_tags()
        if rank == root:
            data = np.ascontiguousarray(data)
            comm.send(data.shape, dest=recv_rank, tag=tag_s)
            comm.send(data.dtype, dest=recv_rank, tag=tag_t)
            comm.Send(data, dest=recv_rank, tag=tag_d)
            return None
        if rank == recv_rank:
            shape = comm.recv(source=root, tag=tag_s)
            dtype = comm.recv(source=root, tag=tag_t)
            buf = recv_buff if recv_buff is not None \
                else np.empty(shape, dtype=dtype)
            comm.Recv(buf, source=root, tag=tag_d)
            return buf
        return None

    if mdtype == "Gather":
        data = np.ascontiguousarray(data)
        if rank == root:
            recv_shape = [size] + list(data.shape)
            buf = recv_buff if recv_buff is not None \
                else np.empty(recv_shape, dtype=data.dtype)
        else:
            buf = None
        comm.Gather(data, buf, root=root)
        return buf if rank == root else None

    if mdtype == "TGather":
        data = np.moveaxis(data, source=axis, destination=0)
        data_shape = list(data.shape)
        data = np.ascontiguousarray(data)
        if rank == root:
            buf = recv_buff if recv_buff is not None \
                else np.empty([size] + data_shape, dtype=data.dtype)
        else:
            buf = None
        comm.Gather(data, buf, root=root)
        if rank != root:
            return None
        buf = np.moveaxis(buf, source=0, destination=1)
        buf = buf.reshape(tuple([size * data_shape[0]] + data_shape[1:]))
        return np.moveaxis(buf, source=0, destination=axis)

    if mdtype == "Allgather":
        data = np.ascontiguousarray(data)
        buf = recv_buff if recv_buff is not None \
            else np.empty([size] + list(data.shape), dtype=data.dtype)
        comm.Allgather(data, buf)
        return buf

    if mdtype == "Bcast":
        if rank == root:
            data_np = np.asarray(data)
            shape, dtype = data_np.shape, data_np.dtype
        else:
            shape = dtype = None
        shape = comm.bcast(shape, root=root)
        dtype = comm.bcast(dtype, root=root)
        if recv_buff is not None:
            buf = recv_buff
        else:
            buf = np.empty(shape, dtype=dtype)
        if rank == root:
            np.copyto(buf, data_np.reshape(buf.shape))
        comm.Bcast(buf, root=root)
        return buf

    if mdtype == "Scatter":
        if rank == root:
            data = np.moveaxis(data, source=axis, destination=0)
            n_len = data.shape[0]
        else:
            n_len = None
        n_len = comm.bcast(n_len, root=root)
        if n_len % size != 0:
            raise ValueError(
                f"Scatter: axis-0 size {n_len} not divisible by {size}; "
                "use TScatter")
        if rank == root:
            data = data.reshape([size, n_len // size] + list(data.shape)[1:])
            shape, dtype = list(data.shape)[1:], data.dtype
            data = np.ascontiguousarray(data)
        else:
            shape = dtype = None
        shape = comm.bcast(shape, root=root)
        dtype = comm.bcast(dtype, root=root)
        buf = recv_buff if recv_buff is not None \
            else np.empty(shape, dtype=dtype)
        comm.Scatter(data, buf, root=root)
        return np.moveaxis(buf, source=0, destination=axis)

    if mdtype == "TScatter":
        if rank == root:
            data = np.moveaxis(data, source=axis, destination=0)
            n_len = data.shape[0]
            n_main = (n_len // size) * size
            rem = n_len % size
            data_rem = data[n_main:].copy() if rem else None
            data = data[:n_main]
            data = np.moveaxis(
                data.reshape([n_main // size, size] + list(data.shape)[1:]),
                source=1, destination=0)
            shape, dtype = list(data.shape)[1:], data.dtype
            data = np.ascontiguousarray(data)
        else:
            rem = shape = dtype = None
        rem = comm.bcast(rem, root=root)
        shape = comm.bcast(shape, root=root)
        dtype = comm.bcast(dtype, root=root)
        buf = np.empty(shape, dtype=dtype)
        comm.Scatter(data, buf, root=root)
        tag_off = _TAG_RESERVE
        for i in range(rem):
            dest = i % size
            base = tag_off + root * 1024 + i * 3
            if rank == root:
                rd = np.ascontiguousarray(np.asarray([data_rem[i]]))
                if dest == root:
                    buf = np.append(buf, rd, axis=0)
                else:
                    comm.send(rd.shape, dest=dest, tag=base + 1)
                    comm.send(rd.dtype, dest=dest, tag=base + 2)
                    comm.Send(rd, dest=dest, tag=base)
            elif rank == dest:
                rshape = comm.recv(source=root, tag=base + 1)
                rdtype = comm.recv(source=root, tag=base + 2)
                rbuf = np.empty(rshape, dtype=rdtype)
                comm.Recv(rbuf, source=root, tag=base)
                buf = np.append(buf, rbuf, axis=0)
        return np.moveaxis(buf, source=0, destination=axis)

    # Transport — Gather → TScatter
    data_in = np.ascontiguousarray(data) if data is not None else data
    gathered = get_mpi_data(data=data_in, mdtype="Gather", root=root,
                            axis=axis)
    if rank == root and gathered is not None:
        gathered = np.ascontiguousarray(gathered)
    return get_mpi_data(data=gathered, mdtype="TScatter", root=root,
                        axis=axis)
