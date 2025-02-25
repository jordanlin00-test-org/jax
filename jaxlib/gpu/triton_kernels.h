#ifndef JAXLIB_GPU_TRITON_H_
#define JAXLIB_GPU_TRITON_H_

#include <cstdint>
#include <memory>
#include <string>
#include <tuple>
#include <variant>
#include <vector>

#include "absl/cleanup/cleanup.h"
#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "absl/synchronization/mutex.h"
#include "jaxlib/gpu/triton.pb.h"
#include "jaxlib/gpu/vendor.h"
#include "xla/service/custom_call_status.h"

namespace jax::JAX_GPU_NAMESPACE {

void TritonKernelCall(CUstream stream, void** buffers, const char* opaque,
                      size_t opaque_len, XlaCustomCallStatus* status);

class ModuleImage;

class Kernel {
 public:
  Kernel(std::string kernel_name, uint32_t num_warps, uint32_t shared_mem_bytes,
         std::string ptx, std::string ttir, int compute_capability);

  absl::Status Launch(CUstream stream, uint32_t grid[3], void** params);

  static Kernel FromProto(const jax_triton::TritonKernel& proto);
  jax_triton::TritonKernel ToProto() const;

 private:
  std::string kernel_name_;
  uint32_t block_dim_x_;
  uint32_t shared_mem_bytes_;
  std::string ptx_;
  std::string ttir_;
  int compute_capability_;

  ModuleImage* module_image_ = nullptr;
};

class KernelCall {
 public:
  struct Parameter {
    struct Array {
      size_t bytes_to_zero;
      size_t ptr_divisibility;
    };

    static absl::StatusOr<Parameter> FromProto(
        const jax_triton::TritonKernelCall_Parameter& proto);
    jax_triton::TritonKernelCall_Parameter ToProto() const;

    std::variant<Array, bool, int32_t, uint32_t, int64_t, uint64_t> value;
  };

  KernelCall(Kernel kernel, uint32_t grid_0, uint32_t grid_1, uint32_t grid_2,
             std::vector<Parameter> parameters);

  absl::Status Launch(CUstream stream, void** buffers);

  static absl::StatusOr<KernelCall> FromProto(
      const jax_triton::TritonKernelCall& proto);
  jax_triton::TritonKernelCall ToProto() const;

 private:
  Kernel kernel_;
  uint32_t grid_[3];
  std::vector<Parameter> parameters_;
};

class AutotunedKernelCall {
 public:
  struct Config {
    KernelCall kernel_call;
    std::string description;
  };

  AutotunedKernelCall(
      std::string name, std::vector<Config> configs,
      std::vector<std::tuple<size_t, size_t, size_t>> input_output_aliases);

  static absl::StatusOr<KernelCall> Autotune(AutotunedKernelCall kernel_call,
                                             CUstream stream, void** buffers);

  static absl::StatusOr<AutotunedKernelCall> FromProto(
      const jax_triton::TritonAutotunedKernelCall& proto);
  jax_triton::TritonAutotunedKernelCall ToProto() const;

 private:
  std::string name_;
  std::vector<Config> configs_;
  // (input buffer idx, output buffer idx, size)
  std::vector<std::tuple<size_t, size_t, size_t>> input_output_aliases_;
};

absl::StatusOr<std::string> ZlibUncompress(absl::string_view compressed);

}  // namespace jax::JAX_GPU_NAMESPACE

#endif  // JAXLIB_GPU_TRITON_H_
