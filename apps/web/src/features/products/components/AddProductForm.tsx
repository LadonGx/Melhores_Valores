import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { useAddProduct } from '../hooks/useProducts';
import styles from './AddProductForm.module.css';

const schema = z.object({
  url: z.string().url('URL inválida').min(1, 'URL é obrigatória'),
});

type FormValues = z.infer<typeof schema>;

interface AddProductFormProps {
  onSuccess?: () => void;
}

export function AddProductForm({ onSuccess }: AddProductFormProps) {
  const { mutate, isPending, error, isSuccess } = useAddProduct();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = (data: FormValues) => {
    mutate(data.url, {
      onSuccess: () => {
        reset();
        onSuccess?.();
      },
    });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className={styles.form}>
      <Input
        label="URL do Produto"
        placeholder="https://www.amazon.com.br/dp/..."
        hint="Suporta Amazon, Mercado Livre e AliExpress."
        error={errors.url?.message}
        {...register('url')}
      />
      {error && <p className={styles.apiError}>{error.message}</p>}
      {isSuccess && (
        <p className={styles.success}>
          Produto enviado para processamento. Pode levar alguns segundos para aparecer na lista.
        </p>
      )}
      <Button type="submit" loading={isPending}>
        Adicionar para monitorar
      </Button>
    </form>
  );
}
