# El rol de la máquina de staging ya existe: lo creó a mano la guía de staging (INV-34, §1) y lo usa la máquina de
# compose. OpenTofu lo adopta en lugar de crearlo (el primer plan muestra «import»), y desde ahí le agrega los permisos
# de Parameter Store, el agente de CloudWatch y la escritura de volcados. La máquina de compose sigue funcionando igual
# con más permisos, hasta que se apague en el corte (fase 5)

import {
  to = module.ambiente.aws_iam_role.maquina
  id = "inventaio-staging-ec2"
}

# La consola crea el perfil de instancia con el mismo nombre del rol
import {
  to = module.ambiente.aws_iam_instance_profile.maquina
  id = "inventaio-staging-ec2"
}

import {
  to = module.ambiente.aws_iam_role_policy.maquina
  id = "inventaio-staging-ec2:inventaio-staging"
}

import {
  to = module.ambiente.aws_iam_role_policy_attachment.ssm
  id = "inventaio-staging-ec2/arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
