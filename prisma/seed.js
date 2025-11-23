import { PrismaClient } from '@prisma/client';
import { destinos } from '../src/data/destinos.js';

const prisma = new PrismaClient();

async function main() {
  console.log('🌎 Insertando destinos desde src/data/destinos.js...');

  if (!destinos || destinos.length === 0) {
    console.log('❌ No hay destinos definidos en el archivo local.');
    return;
  }

  // Eliminar datos anteriores
  await prisma.destino.deleteMany();
  console.log('🧹 Datos anteriores eliminados.');

  // Insertar nuevos datos
  for (const d of destinos) {
    await prisma.destino.create({
      data: {
        id: d.id, // ahora es String
        slug: d.slug || d.id, // usa el slug del data
        nombre: d.nombre,
        ubicacion: d.ubicacion,
        tipo: d.tipo,
        precio: d.precio,
        duracion: d.duracion,
        presupuesto: d.presupuesto,
        imagen: d.imagen,
        descripcion: d.descripcion,
        gastos: d.gastos,
        tours: d.tours,
      },
    });
  }

  console.log(`✅ ${destinos.length} destinos insertados correctamente.`);
}

main()
  .catch((e) => {
    console.error('❌ Error al insertar destinos:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
