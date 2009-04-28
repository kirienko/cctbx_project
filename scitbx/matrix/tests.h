#ifndef SCITBX_MATRIX_TESTS_H
#define SCITBX_MATRIX_TESTS_H

#include <scitbx/array_family/accessors/mat_grid.h>
#include <scitbx/array_family/versa_matrix.h>
#include <scitbx/array_family/ref_algebra.h>
#include <scitbx/matrix/norms.h>
#include <limits>
#include <cmath>

namespace scitbx { namespace matrix {

template <typename T>
T normality_ratio(af::const_ref<T, af::mat_grid> const &u,
                  T eps=std::numeric_limits<T>::epsilon())
{
  SCITBX_ASSERT(u.is_square());
  int n = u.n_rows();
  af::versa<T, af::c_grid<2> > delta = af::matrix_multiply(
        u, af::matrix_transpose(u).ref());
  af::ref<T, af::c_grid<2> > delta_ = delta.ref();
  for (int i=0; i<n; ++i) delta_(i,i)--;
  return (norm_1(delta.const_ref())/n)/eps;
}

template <typename T>
T equality_ratio(af::const_ref<T, af::mat_grid> const &a,
                 af::const_ref<T, af::mat_grid> const &b,
                 T eps=std::numeric_limits<T>::epsilon())
{
  SCITBX_ASSERT(a.n_rows() == b.n_rows());
  SCITBX_ASSERT(a.n_columns() == b.n_columns());
  typedef af::c_grid<2> dim;
  int m=a.n_rows(), n=a.n_columns();
  af::versa<T, dim> delta(dim(m, n));
  for (int i=0; i<m; ++i) for (int j=0; j<n; ++j) delta(i,j) = a(i,j) - b(i,j);
  return ((norm_1(delta.const_ref())
           /std::max(a.n_rows(), a.n_columns()))
           /norm_1(a))/eps;
}


}} // scitbx::matrix

#endif // GUARD
